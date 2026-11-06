//! Tauri shell: spawns the PyInstaller backend sidecar, waits for
//! readiness, then navigates the webview to the backend-served SPA
//! (same-origin so httpOnly cookies stay first-party over plain HTTP).

use std::io::Read;
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::Manager;
use tauri_plugin_updater::UpdaterExt;

struct AppState {
    child: Mutex<Option<Child>>,
    port: u16,
    data_dir: PathBuf,
}

/// Find the pid holding a LISTEN socket on `port` by matching the socket
/// inode between /proc/net/tcp and /proc/*/fd (Linux-only, like
/// kill_process_tree below).
fn find_listener_pid(port: u16) -> Option<u32> {
    // /proc/net/tcp columns: sl local_address rem_address st … inode —
    // addresses are hex "AABBCCDD:PORT", st 0A = LISTEN, inode is field 9.
    let mut wanted_inode: Option<String> = None;
    let tcp = std::fs::read_to_string("/proc/net/tcp").ok()?;
    for line in tcp.lines().skip(1) {
        let fields: Vec<&str> = line.split_whitespace().collect();
        if fields.len() < 10 || fields[3] != "0A" {
            continue;
        }
        if let Some((_, port_hex)) = fields[1].rsplit_once(':')
            && u16::from_str_radix(port_hex, 16).ok() == Some(port)
        {
            wanted_inode = Some(fields[9].to_string());
            break;
        }
    }
    let inode = wanted_inode?;
    let needle = format!("socket:[{inode}]");
    for entry in std::fs::read_dir("/proc").ok()?.flatten() {
        let Ok(pid) = entry.file_name().to_string_lossy().parse::<u32>() else {
            continue;
        };
        let Ok(fds) = std::fs::read_dir(format!("/proc/{pid}/fd")) else {
            continue;
        };
        for fd in fds.flatten() {
            if let Ok(link) = std::fs::read_link(fd.path())
                && link.to_string_lossy() == needle
            {
                return Some(pid);
            }
        }
    }
    None
}

/// True when the pid is one of our PyInstaller sidecars (stale orphan from a
/// crashed session — never the dev server or an unrelated process).
fn is_our_sidecar(pid: u32) -> bool {
    std::fs::read_to_string(format!("/proc/{pid}/cmdline"))
        .map(|cmd| cmd.contains("health-manager-backend"))
        .unwrap_or(false)
}

/// Kill a stale sidecar and wait for it to release `port`.
fn reclaim_port(pid: u32, port: u16) -> bool {
    kill_process_tree(pid);
    let deadline = Instant::now() + Duration::from_secs(5);
    while Instant::now() < deadline {
        if TcpStream::connect(("127.0.0.1", port)).is_err() {
            return true;
        }
        thread::sleep(Duration::from_millis(200));
    }
    false
}

fn pick_stable_port(data_dir: &std::path::Path) -> u16 {
    // Persist the port so the webview origin (localStorage/SW scope
    // includes it) stays stable across launches. If the port is held by a
    // stale sidecar from a crashed/killed session (kill_process_tree in
    // kill_sidecar can't run on SIGKILL), reclaim it instead of spawning a
    // second backend on a random port and orphaning the first.
    let port_file = data_dir.join("backend.port");
    if let Ok(text) = std::fs::read_to_string(&port_file)
        && let Ok(port) = text.trim().parse::<u16>()
    {
        if TcpStream::connect(("127.0.0.1", port)).is_err() {
            return port; // free — reuse it
        }
        if let Some(pid) = find_listener_pid(port)
            && is_our_sidecar(pid)
            && reclaim_port(pid, port)
        {
            return port; // reclaimed — origin stays stable
        }
    }
    // Bind :0 and read the assigned port.
    std::net::TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr().map(|a| a.port()))
        .unwrap_or(8321)
}

fn wait_until_ready(port: u16, timeout: Duration) -> bool {
    // Raw HTTP/1.0 GET: a TCP connect is not enough — uvicorn binds
    // before the lifespan (migrations) finishes.
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if let Ok(mut stream) = TcpStream::connect(("127.0.0.1", port)) {
            let request = format!("GET /api/v1/health/ready HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n\r\n");
            if std::io::Write::write_all(&mut stream, request.as_bytes()).is_ok() {
                // Status line: "HTTP/1.1 200 OK" — bytes 9..12 are the
                // status code regardless of version formatting.
                let mut first = [0u8; 12];
                if stream.read_exact(&mut first).is_ok()
                    && first.starts_with(b"HTTP/")
                    && &first[9..12] == b"200"
                {
                    return true;
                }
            }
        }
        thread::sleep(Duration::from_millis(500));
    }
    false
}

fn spawn_backend(resource_dir: &PathBuf, port: u16, data_dir: &PathBuf) -> std::io::Result<Child> {
    // Resource mapping "binaries/health-manager-backend/": "backend/"
    // FLATTENS the onedir — the binary lands directly under backend/.
    let exe = resource_dir.join("backend/health-manager-backend");
    if !exe.exists() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::NotFound,
            format!("sidecar missing: {}", exe.display()),
        ));
    }
    let log = std::fs::File::create(data_dir.join("backend.log"))?;
    let log_err = log.try_clone()?;
    Command::new(exe)
        .arg(format!("--port={port}"))
        .env("APP_ENV", "desktop")
        .env("HM_PORT", port.to_string())
        .current_dir(data_dir)
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(log_err))
        .spawn()
}

fn kill_process_tree(pid: u32) {
    // Collect descendants via /proc, SIGTERM all, then SIGKILL survivors.
    let mut to_kill: Vec<i32> = vec![pid as i32];
    loop {
        let mut grew = false;
        if let Ok(entries) = std::fs::read_dir("/proc") {
            for entry in entries.flatten() {
                let name = entry.file_name().into_string().unwrap_or_default();
                let Ok(ppid) = name.parse::<i32>() else { continue };
                let Ok(stat) = std::fs::read_to_string(format!("/proc/{ppid}/stat")) else { continue };
                // ppid is the 4th field, but comm may contain spaces → find last ')'.
                let Some(rest) = stat.rsplit_once(')').map(|(_, r)| r) else { continue };
                let fields: Vec<&str> = rest.split_whitespace().collect();
                if fields.len() < 2 {
                    continue;
                }
                let parent = fields[1].parse::<i32>().unwrap_or(-1);
                if to_kill.contains(&parent) && !to_kill.contains(&ppid) {
                    to_kill.push(ppid);
                    grew = true;
                }
            }
        }
        if !grew {
            break;
        }
    }
    for p in &to_kill {
        unsafe { libc::kill(*p, libc::SIGTERM); }
    }
    thread::sleep(Duration::from_millis(600));
    for p in &to_kill {
        unsafe { libc::kill(*p, libc::SIGKILL); }
    }
}

fn boot(app: &tauri::AppHandle) -> Result<(), String> {
    let resource_dir = app.path().resource_dir().map_err(|e| e.to_string())?;
    let state = app.state::<AppState>();
    let data_dir = state.data_dir.clone();
    let port = state.port;

    let child = spawn_backend(&resource_dir, port, &data_dir)
        .map_err(|e| format!("failed to spawn backend: {e}"))?;
    *state.child.lock().unwrap() = Some(child);

    // Mirror backend output to our stderr for debugging.
    // (The log file is the source of truth; see get_boot_log.)

    if !wait_until_ready(port, Duration::from_secs(90)) {
        return Err(format!("backend not ready on port {port} after 90s"));
    }
    let url = tauri::Url::parse(&format!("http://127.0.0.1:{port}/")).map_err(|e| e.to_string())?;
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.navigate(url);
    }
    Ok(())
}

#[tauri::command]
fn retry_backend(app: tauri::AppHandle) -> Result<(), String> {
    boot(&app)
}

#[tauri::command]
fn get_boot_log(app: tauri::AppHandle) -> String {
    let state = app.state::<AppState>();
    std::fs::read_to_string(state.data_dir.join("backend.log"))
        .unwrap_or_else(|_| "no log yet".into())
}

#[tauri::command]
fn quit_app(app: tauri::AppHandle) {
    app.exit(0);
}

#[derive(Serialize)]
#[serde(rename_all = "snake_case", tag = "status")]
enum UpdateCheck {
    /// An update is available for install.
    Available { version: String, notes: Option<String> },
    /// Already on the latest version.
    UpToDate,
    /// Updater not configured: FHM_UPDATE_MANIFEST_URL / FHM_UPDATE_PUBKEY unset.
    NotConfigured,
    // Check failures are returned as Err(String) — the frontend toasts them.
}

fn updater_from_env(app: &tauri::AppHandle) -> Result<tauri_plugin_updater::Updater, String> {
    let endpoint = std::env::var("FHM_UPDATE_MANIFEST_URL")
        .ok()
        .filter(|v| !v.is_empty())
        .ok_or_else(|| "Updater not configured".to_string())?;
    let pubkey = std::env::var("FHM_UPDATE_PUBKEY")
        .ok()
        .filter(|v| !v.is_empty())
        .ok_or_else(|| "Updater not configured".to_string())?;

    // The updater is runtime-configured (not baked into tauri.conf.json) so the
    // same .deb works for users who never set up an update server: the manifest
    // URL and minisign public key come from the environment. Without them
    // "check for updates" simply reports not-configured instead of failing.
    let builder = app
        .updater_builder()
        .endpoints(vec![endpoint
            .parse()
            .map_err(|e| format!("invalid FHM_UPDATE_MANIFEST_URL: {e}"))?])
        .map_err(|e| e.to_string())?
        .pubkey(pubkey);
    builder.build().map_err(|e| e.to_string())
}

/// Check the self-hosted update manifest.
#[tauri::command]
async fn check_for_updates(app: tauri::AppHandle) -> Result<UpdateCheck, String> {
    let updater = match updater_from_env(&app) {
        Ok(u) => u,
        Err(_) => return Ok(UpdateCheck::NotConfigured),
    };
    match updater.check().await {
        Ok(Some(update)) => Ok(UpdateCheck::Available {
            version: update.version.clone(),
            notes: update.body.clone(),
        }),
        Ok(None) => Ok(UpdateCheck::UpToDate),
        Err(e) => Err(e.to_string()),
    }
}

/// Download + install the pending update, then restart the app.
/// Must be preceded by a successful check_for_updates in the same session.
#[tauri::command]
async fn install_update(app: tauri::AppHandle) -> Result<(), String> {
    let updater = updater_from_env(&app)?;
    let update = updater
        .check()
        .await
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "No update available".to_string())?;

    update
        .download_and_install(
            |_chunk, _total| {}, // progress UI is a toast on the JS side; the
            || {},               // install is restart-gated anyway
        )
        .await
        .map_err(|e| e.to_string())?;

    app.restart();
}

pub fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // Second launch: focus the existing window.
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let data_dir = dirs_data();
            std::fs::create_dir_all(data_dir.join("data")).ok();
            let port = pick_stable_port(&data_dir);
            std::fs::write(data_dir.join("backend.port"), port.to_string()).ok();
            app.manage(AppState {
                child: Mutex::new(None),
                port,
                data_dir,
            });

            let handle = app.handle().clone();
            thread::spawn(move || {
                if let Err(err) = boot(&handle) {
                    eprintln!("boot failed: {err}");
                    if let Some(window) = handle.get_webview_window("main") {
                        let _ = window.navigate(tauri::Url::parse("tauri://localhost/error.html").unwrap());
                    }
                }
            });

            // Tray: Show / Quit.
            let tray = tauri::menu::MenuBuilder::new(app)
                .text("show", "Show")
                .text("quit", "Quit")
                .build()?;
            let tray_handle = app.tray_by_id("main-tray").expect("tray icon configured");
            tray_handle.set_menu(Some(tray))?;
            tray_handle.on_menu_event(|app, event| match event.id().as_ref() {
                "show" => {
                    if let Some(w) = app.get_webview_window("main") {
                        let _ = w.show();
                        let _ = w.set_focus();
                    }
                }
                "quit" => app.exit(0),
                _ => {}
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            retry_backend,
            get_boot_log,
            quit_app,
            check_for_updates,
            install_update
        ])
        .build(tauri::generate_context!())
        .expect("error building tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::ExitRequested { .. } = event {
                kill_sidecar(&app_handle.state::<AppState>().child);
            }
        });
}

fn kill_sidecar(mutex: &Mutex<Option<Child>>) {
    let pid = mutex.lock().unwrap().as_ref().map(|c| c.id());
    if let Some(pid) = pid {
        kill_process_tree(pid);
    }
    if let Ok(mut guard) = mutex.try_lock() {
        if let Some(child) = guard.as_mut() {
            let _ = child.kill();
        }
    }
}

fn dirs_data() -> PathBuf {
    // ~/.local/share/com.healthmanager.v2
    if let Ok(xdg) = std::env::var("XDG_DATA_HOME") {
        if !xdg.is_empty() {
            return PathBuf::from(xdg).join("com.healthmanager.v2");
        }
    }
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
    PathBuf::from(home)
        .join(".local/share/com.healthmanager.v2")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_listener_pid() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        assert_eq!(find_listener_pid(port), Some(std::process::id()));
    }

    #[test]
    fn closed_port_has_no_listener_pid() {
        // Take a port just long enough to know it was free, then drop it.
        let port = std::net::TcpListener::bind("127.0.0.1:0")
            .unwrap()
            .local_addr()
            .unwrap()
            .port();
        assert_eq!(find_listener_pid(port), None);
    }

    #[test]
    fn test_process_is_not_our_sidecar() {
        // The test harness binary is never named health-manager-backend,
        // so a stale-sidecar check must not match it.
        assert!(!is_our_sidecar(std::process::id()));
    }
}
