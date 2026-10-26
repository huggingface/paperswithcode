/**
 * MethodFigure: 3-tier fallback chain:
 *   1. Hand-drawn SVG keyed by canonical slug (this dictionary).
 *   2. method.image_url — covers ~95% of methods in live DB.
 *   3. GenericFig — shaped, captioned schematic.
 */

import React from "react";

import type { Method } from "@/lib/api/catalog.types";

// Vaswani-style box palette
const C = {
  pink: "#F8D7D9",
  pinkS: "#D9B0B3",
  yellow: "#FBEFC2",
  yellowS: "#C9B97D",
  orange: "#F8D7B3",
  orangeS: "#C99466",
  blue: "#CDE2EE",
  blueS: "#7FA4BA",
  purple: "#D4D2EA",
  purpleS: "#8E8AC0",
  green: "#CCE2C5",
  greenS: "#7DA475",
  ink: "#1A1814",
  faint: "#8E8678",
};

interface MFBoxProps {
  x: number;
  y: number;
  w: number;
  h: number;
  fill: string;
  stroke: string;
  label?: string;
  fontSize?: number;
}

const MFBox: React.FC<MFBoxProps> = ({ x, y, w, h, fill, stroke, label, fontSize = 10 }) => (
  <g>
    <rect x={x} y={y} width={w} height={h} rx="3" ry="3" fill={fill} stroke={stroke} strokeWidth="1" />
    <text x={x + w / 2} y={y + h / 2} fontSize={fontSize} fontFamily="var(--sans)" fill={C.ink} textAnchor="middle" dominantBaseline="middle">
      {label}
    </text>
  </g>
);

const AttentionFig: React.FC = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: "block" }}>
    <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Scaled Dot-Product Attention</text>
    <MFBox x={140} y={40} w={80} h={26} fill={C.yellow} stroke={C.yellowS} label="MatMul" fontSize={11} />
    <path d="M180 66 L180 80" stroke={C.ink} />
    <MFBox x={140} y={80} w={80} h={26} fill={C.green} stroke={C.greenS} label="SoftMax" fontSize={11} />
    <path d="M180 106 L180 120" stroke={C.ink} />
    <MFBox x={140} y={120} w={80} h={26} fill={C.purple} stroke={C.purpleS} label="Mask (opt.)" fontSize={11} />
    <path d="M180 146 L180 160" stroke={C.ink} />
    <MFBox x={140} y={160} w={80} h={26} fill={C.blue} stroke={C.blueS} label="Scale ÷√dₖ" fontSize={11} />
    <path d="M180 186 L180 200" stroke={C.ink} />
    <MFBox x={140} y={200} w={80} h={26} fill={C.yellow} stroke={C.yellowS} label="MatMul" fontSize={11} />
    <path d="M156 226 L120 270" stroke={C.ink} />
    <path d="M180 226 L180 270" stroke={C.ink} />
    <path d="M204 226 L240 270" stroke={C.ink} />
    <MFBox x={100} y={270} w={40} h={24} fill={C.pink} stroke={C.pinkS} label="Q" fontSize={13} />
    <MFBox x={160} y={270} w={40} h={24} fill={C.pink} stroke={C.pinkS} label="K" fontSize={13} />
    <MFBox x={220} y={270} w={40} h={24} fill={C.pink} stroke={C.pinkS} label="V" fontSize={13} />
    <text x="180" y="330" fontSize="14" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">
      softmax(QK
      <tspan fontSize="9" baselineShift="super">⊤</tspan>
      {" / √d) V"}
    </text>
  </svg>
);

const ContrastiveFig: React.FC = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: "block" }}>
    <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Contrastive learning</text>
    <MFBox x={120} y={40} w={120} h={26} fill={C.blue} stroke={C.blueS} label="Input x" fontSize={11} />
    <path d="M180 66 V76 M90 76 H270 M90 76 V88 M270 76 V88" stroke={C.ink} />
    <MFBox x={35} y={88} w={110} h={26} fill={C.yellow} stroke={C.yellowS} label="Augment t₁" fontSize={11} />
    <MFBox x={215} y={88} w={110} h={26} fill={C.yellow} stroke={C.yellowS} label="Augment t₂" fontSize={11} />
    <path d="M90 114 V138 M270 114 V138" stroke={C.ink} />
    <MFBox x={35} y={138} w={110} h={26} fill={C.orange} stroke={C.orangeS} label="Encoder f" fontSize={11} />
    <MFBox x={215} y={138} w={110} h={26} fill={C.orange} stroke={C.orangeS} label="Encoder f" fontSize={11} />
    <text x="180" y="155" fontSize="9" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">shared weights</text>
    <path d="M90 164 V188 M270 164 V188" stroke={C.ink} />
    <MFBox x={35} y={188} w={110} h={26} fill={C.purple} stroke={C.purpleS} label="Projection g" fontSize={11} />
    <MFBox x={215} y={188} w={110} h={26} fill={C.purple} stroke={C.purpleS} label="Projection g" fontSize={11} />
    <path d="M90 214 V238 M270 214 V238" stroke={C.ink} />
    <MFBox x={35} y={238} w={110} h={26} fill={C.pink} stroke={C.pinkS} label="z₁" fontSize={13} />
    <MFBox x={215} y={238} w={110} h={26} fill={C.pink} stroke={C.pinkS} label="z₂" fontSize={13} />
    <path d="M145 251 H215" stroke={C.greenS} strokeWidth="1.5" strokeDasharray="4 3" />
    <text x="180" y="244" fontSize="9" fontFamily="var(--sans)" fill={C.greenS} textAnchor="middle">attract</text>
    <text x="180" y="318" fontSize="12" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">Positive pair: pull together</text>
    <text x="180" y="336" fontSize="12" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">Other samples: push apart</text>
    <text x="180" y="370" fontSize="11" fontFamily="var(--serif)" fill={C.faint} textAnchor="middle">InfoNCE: maximize sim(z₁, z₂) / τ</text>
  </svg>
);

const AGENT_SKILL_TREE_LINES: ReadonlyArray<readonly [string, string]> = [
  ["my-skill/", ""],
  ["├── SKILL.md", "# Required: metadata + instructions"],
  ["├── scripts/", "# Optional: executable code"],
  ["├── references/", "# Optional: documentation"],
  ["├── assets/", "# Optional: templates, resources"],
  ["└── ...", "# Any additional files or directories"],
];

const AgentSkillsFig: React.FC = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: "block" }}>
    <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">
      Skill package layout
    </text>
    <rect x="28" y="48" width="304" height="318" rx="8" fill="#FFFDF8" stroke={C.faint} strokeWidth="1" />
    {AGENT_SKILL_TREE_LINES.map(([entry, comment], index) => {
      const y = 92 + index * 44;
      return (
        <g key={entry}>
          <text x="44" y={y} fontSize="11" fontFamily="var(--mono)" fill={C.ink} dominantBaseline="middle">
            {entry}
          </text>
          {comment ? (
            <text x="138" y={y} fontSize="8.5" fontFamily="var(--mono)" fill={C.faint} dominantBaseline="middle">
              {comment}
            </text>
          ) : null}
        </g>
      );
    })}
  </svg>
);

const FIGURE_BY_SLUG: Record<string, React.FC> = {
  attention: AttentionFig,
  "contrastive-learning": ContrastiveFig,
  "agent-skills": AgentSkillsFig,
};

const GenericFig: React.FC<{ method: Pick<Method, "name"> }> = ({ method }) => (
  <svg viewBox="0 0 360 420" width="100%" height="100%">
    <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">
      {method.name || "method"}
    </text>
    <MFBox x={80} y={70} w={200} h={50} fill={C.blue} stroke={C.blueS} label="Input" fontSize={12} />
    <path d="M180 120 L180 150" stroke={C.ink} />
    <MFBox x={80} y={150} w={200} h={70} fill={C.orange} stroke={C.orangeS} label={method.name || "transform"} fontSize={13} />
    <path d="M180 220 L180 250" stroke={C.ink} />
    <MFBox x={80} y={250} w={200} h={50} fill={C.purple} stroke={C.purpleS} label="Output" fontSize={12} />
  </svg>
);

interface MethodFigureProps {
  method: Pick<Method, "slug" | "name" | "image_url">;
}

export const MethodFigure: React.FC<MethodFigureProps> = ({ method }) => {
  const slug = (method.slug || "").toLowerCase();
  const FigFromDict = FIGURE_BY_SLUG[slug];
  if (FigFromDict) {
    return (
      <div className="method-figure-svg method-figure-svg--schematic">
        <FigFromDict />
      </div>
    );
  }
  if (method.image_url) {
    const sizeClass =
      slug === "transformer" ||
      slug === "gpt-4" ||
      slug === "gpt-4o" ||
      slug === "multi-head-attention"
        ? " method-figure-svg--compact"
        : slug === "rpn"
          ? " method-figure-svg--scaled-80"
          : "";
    return (
      <div
        className={`method-figure-svg method-figure-svg--image${sizeClass}`}
      >
        <img
          className="method-figure-img"
          src={method.image_url}
          alt={`${method.name} figure`}
        />
      </div>
    );
  }
  return (
    <div className="method-figure-svg method-figure-svg--schematic">
      <GenericFig method={method} />
    </div>
  );
};
