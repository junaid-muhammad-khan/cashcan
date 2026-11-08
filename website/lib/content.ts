// Copy shared by the home page and the standalone pages (how it works, privacy).
export const STEPS = [
  { title: "Step up, get recognised", body: "An opt-in face match identifies you at the bin and links the drop to your Solana wallet. Only face embeddings are stored, never photos." },
  { title: "Two cameras look at the item", body: "A top camera and a front camera capture the item from two angles, so a detection is more reliable and much harder to fool." },
  { title: "Sorted by your city, not by material", body: "The classifier picks Organics, Cans or Waste, then the local rule table says where it really goes and shows a plain-language reason." },
  { title: "Anti-abuse gates", body: "Confidence threshold, camera agreement and a per-user cooldown all have to pass, and the bin has to recognise your face, before anything is paid." },
  { title: "Paid and logged", body: "Reward-eligible items pay out in SOL on devnet. Every decision, paid or rejected, lands in Databricks for the dashboard." },
];

export const GATES = [
  ["Classifier confidence", "0.93 ≥ 0.75"],
  ["Top + front cams agree", "can = can"],
  ["Cooldown since last drop", "41 s ≥ 30 s"],
  ["Face recognised", "your account"],
];

export const PRIVACY = [
  ["Opt-in only", "Nobody is enrolled without a consent screen."],
  ["Embeddings, not photos", "The bin stores a numeric face template. Raw images are never kept."],
  ["Delete on request", "Remove your face data and account at any time."],
];

