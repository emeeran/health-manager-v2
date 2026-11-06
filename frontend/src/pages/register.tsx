import { AuthForm } from "../components/auth-form";
import { register } from "../lib/api/auth";

export default function Register() {
  return <AuthForm mode="register" onSubmit={register} />;
}
