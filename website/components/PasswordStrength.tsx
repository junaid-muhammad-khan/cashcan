// Rough strength hint for the sign-up form. The server only enforces 8+ characters;
// this just nudges people toward longer passwords.
export function passwordScore(pw: string): number {
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[0-9]/.test(pw) && /[a-zA-Z]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw) || pw.length >= 16) score++;
  return score;
}

const COLORS = ["#B4321F", "#C98A00", "#2BB673", "#157A46"];
const LABELS = ["Too short", "Okay", "Good", "Strong", "Very strong"];

export default function PasswordStrength({ password }: { password: string }) {
  const score = passwordScore(password);
  return (
    <div className="strength">
      <div className="segs" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <span key={i} style={{ background: i < score ? COLORS[score - 1] : "#DCE4DD" }} />
        ))}
      </div>
      <p aria-live="polite">{password ? `Strength: ${LABELS[score]}` : "Use a phrase you will remember. Longer is stronger."}</p>
    </div>
  );
}
