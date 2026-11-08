import type { ContainerIcon } from "@/lib/prices";

// Simple flat illustrations of each container type (our own drawings, 64x72 box).
export default function ContainerArt({ icon }: { icon: ContainerIcon }) {
  const common = { width: 64, height: 72, viewBox: "0 0 64 72", "aria-hidden": true } as const;
  switch (icon) {
    case "can":
      return (
        <svg {...common}>
          <ellipse cx="32" cy="66" rx="16" ry="3" fill="#0F1F17" opacity=".08" />
          <path d="M18 14c0-3 6-5 14-5s14 2 14 5v46c0 3-6 5-14 5s-14-2-14-5z" fill="#D6463A" />
          <path d="M18 14c0 3 6 5 14 5s14-2 14-5" fill="none" stroke="#B5352B" strokeWidth="1.5" />
          <ellipse cx="32" cy="12" rx="14" ry="4" fill="#C9D1D6" />
          <rect x="29" y="9" width="6" height="3" rx="1.5" fill="#8C979E" />
          <rect x="18" y="30" width="28" height="14" fill="#2C5F8A" />
          <path d="M22 37h20" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
          <path d="M18 60c0 3 6 5 14 5s14-2 14-5" fill="none" stroke="#B5352B" strokeWidth="1.5" />
        </svg>
      );
    case "plastic-bottle":
      return (
        <svg {...common}>
          <ellipse cx="32" cy="67" rx="13" ry="3" fill="#0F1F17" opacity=".08" />
          <rect x="27" y="3" width="10" height="7" rx="2" fill="#2C5F8A" />
          <path d="M27 10h10v4c6 3 9 7 9 13v35c0 2-2 4-4 4H22c-2 0-4-2-4-4V27c0-6 3-10 9-13z" fill="#CFE8F7" stroke="#8CC6E8" strokeWidth="1.5" />
          <rect x="18" y="34" width="28" height="14" fill="#4E9BD1" />
          <path d="M22 41h20" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
          <path d="M22 54h6" stroke="#fff" strokeWidth="2" strokeLinecap="round" opacity=".7" />
        </svg>
      );
    case "plastic-cup":
      return (
        <svg {...common}>
          <ellipse cx="32" cy="67" rx="13" ry="3" fill="#0F1F17" opacity=".08" />
          <path d="M15 14h34l-5 50H20z" fill="#F2F4F5" stroke="#B9C2C7" strokeWidth="1.5" />
          <path d="M13 11h38v4H13z" fill="#C9D1D6" />
          <path d="M14 11c4-5 14-6 24-3l10 3" fill="#DCE2E6" stroke="#9AA6AD" strokeWidth="1.2" />
          <path d="M21 28h22M22 40h20" stroke="#DCE2E6" strokeWidth="2" />
        </svg>
      );
    case "drink-box":
      return (
        <svg {...common}>
          <ellipse cx="32" cy="67" rx="15" ry="3" fill="#0F1F17" opacity=".08" />
          <path d="M18 16h26v48H18z" fill="#F4F0FA" stroke="#B9A7D6" strokeWidth="1.5" />
          <path d="M44 16l6-4v48l-6 4z" fill="#C9B8E4" />
          <path d="M18 16l6-4h26l-6 4z" fill="#E4DAF2" />
          <path d="M38 12l4-10" stroke="#E3B23C" strokeWidth="2.5" strokeLinecap="round" />
          <rect x="21" y="32" width="20" height="16" rx="3" fill="#7B57B8" />
          <path d="M25 40h12" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
      );
    case "gable-top":
      return (
        <svg {...common}>
          <ellipse cx="32" cy="67" rx="15" ry="3" fill="#0F1F17" opacity=".08" />
          <path d="M19 22h26v42H19z" fill="#FDF6EC" stroke="#E0C9A6" strokeWidth="1.5" />
          <path d="M19 22l13-12 13 12z" fill="#F4E6CF" stroke="#E0C9A6" strokeWidth="1.5" />
          <rect x="29" y="5" width="6" height="5" rx="1" fill="#E07A2E" />
          <rect x="19" y="34" width="26" height="20" fill="#E07A2E" />
          <path d="M24 40h16M24 46h10" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
      );
    case "glass-bottle":
      return (
        <svg {...common}>
          <ellipse cx="32" cy="67" rx="12" ry="3" fill="#0F1F17" opacity=".08" />
          <rect x="28" y="3" width="8" height="5" rx="1.5" fill="#B5832F" />
          <path d="M28 8h8v12c5 3 8 8 8 14v28c0 2-2 4-4 4H24c-2 0-4-2-4-4V34c0-6 3-11 8-14z" fill="#DDEFE4" stroke="#7FB894" strokeWidth="1.5" />
          <rect x="20" y="38" width="24" height="16" rx="2" fill="#C2477A" />
          <path d="M24 46h16" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
          <path d="M24 26c0-3 2-5 4-6" stroke="#fff" strokeWidth="2" strokeLinecap="round" opacity=".7" />
        </svg>
      );
  }
}
