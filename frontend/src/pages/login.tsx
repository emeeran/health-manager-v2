import { AuthForm } from "../components/auth-form";
import { login } from "../lib/api/auth";

export default function Login() {
  return <AuthForm mode="login" onSubmit={login} />;
}
