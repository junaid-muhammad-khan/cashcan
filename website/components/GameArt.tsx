import ContainerArt from "./ContainerArt";
import type { ArtId, BinId } from "@/lib/game";

// Flat drawings for the sorting game, in the same style as the container catalogue (64 x 72 box). Our own artwork.
const BOX = { viewBox: "0 0 64 72", "aria-hidden": true } as const;
const Shadow = ({ w = 14 }: { w?: number }) => <ellipse cx="32" cy="67" rx={w} ry="3" fill="#0F1F17" opacity=".08" />;

export function ItemArt({ id }: { id: ArtId }) {
  switch (id) {
    case "can": return <ContainerArt icon="can" />;
    case "plastic-bottle": return <ContainerArt icon="plastic-bottle" />;
    case "drink-box": return <ContainerArt icon="drink-box" />;
    case "gable-top": return <ContainerArt icon="gable-top" />;
    case "glass-bottle": return <ContainerArt icon="glass-bottle" />;
    case "banana":
      return (
        <svg {...BOX}>
          <Shadow w={20} />
          <path d="M10 22c4 22 20 36 44 30 3-1 3-5 0-5-18 3-30-8-34-27-1-3-7-3-10 2z" fill="#F4D03F" stroke="#C9A227" strokeWidth="1.5" strokeLinejoin="round" />
          <path d="M12 21c1-3 6-4 8-1" stroke="#8C6A1E" strokeWidth="3" strokeLinecap="round" fill="none" />
          <path d="M54 47c3 0 4 3 2 5" stroke="#5B4A1A" strokeWidth="3" strokeLinecap="round" fill="none" />
          <path d="M24 40c6 6 14 8 22 6" stroke="#C9A227" strokeWidth="1.5" strokeLinecap="round" fill="none" />
        </svg>
      );
    case "apple-core":
      return (
        <svg {...BOX}>
          <Shadow />
          <path d="M20 14c2-5 10-5 12-1 2-4 10-4 12 1 2 4-3 7-6 8H26c-3-1-8-4-6-8z" fill="#D6463A" />
          <path d="M26 22h12c-2 8-2 12 0 20H26c2-8 2-12 0-20z" fill="#F7F0DC" stroke="#E2D7B8" strokeWidth="1.5" />
          <ellipse cx="30" cy="31" rx="1.6" ry="2.6" fill="#6B4A2B" /><ellipse cx="35" cy="34" rx="1.6" ry="2.6" fill="#6B4A2B" />
          <path d="M20 50c2-5 10-5 12-1 2-4 10-4 12 1 2 4-3 8-6 8H26c-3 0-8-4-6-8z" fill="#D6463A" />
          <path d="M32 12c0-4 1-7 4-9" stroke="#6B4A2B" strokeWidth="2.4" strokeLinecap="round" fill="none" />
        </svg>
      );
    case "burger":
      return (
        <svg {...BOX}>
          <Shadow w={20} />
          <path d="M10 32c0-14 10-20 22-20s22 6 22 20z" fill="#E0A04A" />
          <circle cx="24" cy="22" r="1.4" fill="#FFF3D1" /><circle cx="33" cy="18" r="1.4" fill="#FFF3D1" /><circle cx="41" cy="24" r="1.4" fill="#FFF3D1" /><circle cx="30" cy="27" r="1.4" fill="#FFF3D1" />
          <path d="M8 34c3 4 6-2 9 2s6-2 9 2 6-2 9 2 6-2 9 2 6-2 8-2v-2H8z" fill="#5DBB63" />
          <rect x="9" y="37" width="46" height="9" rx="4.5" fill="#7A4A2B" />
          <path d="M11 47h42c0 6-4 9-9 9H20c-5 0-9-3-9-9z" fill="#E0A04A" />
        </svg>
      );
    case "fries":
      return (
        <svg {...BOX}>
          <Shadow />
          {[[17, 8, -6], [24, 4, -2], [31, 3, 0], [38, 5, 3], [45, 9, 7]].map(([x, y, r], i) => (
            <rect key={i} x={x} y={y} width="6" height="34" rx="2" fill="#F5C842" stroke="#D9A91F" strokeWidth="1" transform={`rotate(${r} ${x + 3} 40)`} />
          ))}
          <path d="M12 32h40l-4 32H16z" fill="#D6463A" />
          <path d="M12 32h40" stroke="#B5352B" strokeWidth="2" />
          <path d="M20 42h24M21 50h22" stroke="#F5C842" strokeWidth="3" strokeLinecap="round" opacity=".9" />
        </svg>
      );
    case "chip-bag":
      return (
        <svg {...BOX}>
          <Shadow w={18} />
          <path d="M14 8l4 3 4-3 4 3 4-3 4 3 4-3 4 3 4-3 2 6-3 40 3 6-4 3-4-3-4 3-4-3-4 3-4-3-4 3-4-3-4 3-4-3-2-6 3-40z" fill="#E8603C" stroke="#C4482A" strokeWidth="1.5" strokeLinejoin="round" />
          <circle cx="32" cy="34" r="12" fill="#F5C842" />
          <path d="M26 34c2-5 10-5 12 0" stroke="#E8603C" strokeWidth="3" strokeLinecap="round" fill="none" />
          <path d="M17 17v36M47 17v36" stroke="#fff" strokeWidth="1" opacity=".25" />
        </svg>
      );
    case "candy":
      return (
        <svg {...BOX}>
          <Shadow w={20} />
          <path d="M4 22l12 8-12 8z" fill="#E86AA6" /><path d="M60 22l-12 8 12 8z" fill="#E86AA6" />
          <rect x="14" y="20" width="36" height="20" rx="10" fill="#F28AB8" stroke="#D2548C" strokeWidth="1.5" />
          <path d="M22 24l-3 12M30 22l-3 16M38 22l-3 16M46 24l-3 12" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" opacity=".7" />
        </svg>
      );
    case "cup-straw":
      return (
        <svg {...BOX}>
          <Shadow />
          <path d="M40 6V3h6" stroke="#E3B23C" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" fill="none" />
          <path d="M40 6l-4 22" stroke="#E3B23C" strokeWidth="3" strokeLinecap="round" />
          <path d="M16 26h32l-4 38H20z" fill="#F7F7F5" stroke="#C9CFCB" strokeWidth="1.5" />
          <path d="M14 22h36v6H14z" fill="#E8E9E6" stroke="#C9CFCB" strokeWidth="1.5" />
          <path d="M18 40h28l-1 10H19z" fill="#D6463A" />
          <path d="M24 45h16" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
      );
    case "fork":
      return (
        <svg {...BOX}>
          <Shadow w={10} />
          <path d="M22 6v14c0 5 3 8 6 8h2c3 0 6-3 6-8V6" fill="none" stroke="#C7CEC9" strokeWidth="4" strokeLinecap="round" />
          <path d="M28 6v16M32 6v16M36 6v16" stroke="#C7CEC9" strokeWidth="3.4" strokeLinecap="round" />
          <path d="M28 26h8l-1 5c-1 0-1 0-1 0l2 33c0 2-2 3-4 3s-4-1-4-3l2-33z" fill="#D8DDD9" stroke="#B6BEB9" strokeWidth="1.5" strokeLinejoin="round" />
        </svg>
      );
  }
}

/** A bin with a lid that tips open when `open`. Colors come from the game's bin list. */
export function BinArt({ bin, open }: { bin: BinId; open: boolean }) {
  const c = { cans: ["#2BB673", "#157A46"], organics: ["#E3B23C", "#A06E00"], waste: ["#B5BFB9", "#5C6B62"] }[bin];
  return (
    <svg viewBox="0 0 120 120" aria-hidden="true" className="g-bin-art">
      <ellipse cx="60" cy="112" rx="38" ry="5" fill="#0F1F17" opacity=".1" />
      <path d="M26 44h68l-7 64H33z" fill={c[0]} />
      <path d="M26 44h68l-1.4 12H27.4z" fill="#000" opacity=".08" />
      <path d="M44 56l3 44M60 56v44M76 56l-3 44" stroke="#fff" strokeWidth="3" strokeLinecap="round" opacity=".28" />
      <g className={`g-lid${open ? " open" : ""}`} style={{ transformOrigin: "26px 40px" }}>
        <rect x="20" y="30" width="80" height="14" rx="7" fill={c[1]} />
        <rect x="50" y="22" width="20" height="10" rx="5" fill={c[1]} />
      </g>
      {bin === "cans" && <path d="M48 76c4-4 10-4 14 0M55 74v18" stroke="#fff" strokeWidth="4" strokeLinecap="round" fill="none" />}
      {bin === "organics" && <path d="M44 92c8 2 18-4 22-16-10 0-20 6-22 16zM44 92c0-8 4-12 8-14" stroke="#fff" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />}
      {bin === "waste" && <path d="M46 76h28M49 76l3 18h16l3-18M55 72h10" stroke="#fff" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />}
    </svg>
  );
}

export function Heart({ lost }: { lost?: boolean }) {
  return (
    <svg viewBox="0 0 32 30" aria-hidden="true" className={`g-heart${lost ? " lost" : ""}`}>
      <path d="M16 28S2 19 2 9.5C2 5 5.5 2 9.5 2c3 0 5 1.6 6.5 4C17.5 3.6 19.5 2 22.5 2 26.5 2 30 5 30 9.5 30 19 16 28 16 28z"
        fill={lost ? "#DCE4DD" : "#E5484D"} stroke={lost ? "#C5D0C8" : "#B8272C"} strokeWidth="1.5" strokeLinejoin="round" />
      {!lost && <path d="M8 10c0-2.500 1.500-4 3.500-4" stroke="#fff" strokeWidth="2" strokeLinecap="round" fill="none" opacity=".6" />}
    </svg>
  );
}
