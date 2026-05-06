export const AUTH_COOKIE = "examiner_session";

export const ADMIN_USER = {
  id: "admin",
  username: "admin",
  password: "admin",
  name: "Admin",
  email: "admin@example.com",
  initials: "AD",
  workspace: "Examiner",
};

export function isValidSession(value?: string) {
  return value === ADMIN_USER.id;
}

export function verifyCredentials(username: string, password: string) {
  return username === ADMIN_USER.username && password === ADMIN_USER.password;
}
