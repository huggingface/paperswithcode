import React from "react";

import { Icon } from "@/components/Icon";

const HfMonochromeLogo = () => (
  <span className="hf-resource-logo">
    <img
      className="hf-resource-logo-black"
      src="/hf-logo-monochrome-black.svg?v=20260729"
      alt=""
    />
    <img
      className="hf-resource-logo-white"
      src="/hf-logo-monochrome-white.svg?v=20260729"
      alt=""
    />
  </span>
);

const FeedFilterToggle: React.FC<{
  checked: boolean;
  icon: React.ReactNode;
  label: string;
  onChange: (checked: boolean) => void;
}> = ({ checked, icon, label, onChange }) => (
  <button
    type="button"
    className={`paper-feed-filter ${checked ? "active" : ""}`}
    aria-pressed={checked}
    onClick={() => onChange(!checked)}
  >
    <span className="paper-feed-filter-content">
      <span className="paper-feed-filter-icon" aria-hidden="true">
        {icon}
      </span>
      {label}
    </span>
    {checked && (
      <span className="paper-feed-filter-check" aria-hidden="true">
        ✓
      </span>
    )}
  </button>
);

export const PaperFeedFilters: React.FC<{
  hasCode: boolean;
  hasHfArtifacts: boolean;
  onHasCodeChange: (checked: boolean) => void;
  onHasHfArtifactsChange: (checked: boolean) => void;
  showDivider?: boolean;
  showHasCode?: boolean;
}> = ({
  hasCode,
  hasHfArtifacts,
  onHasCodeChange,
  onHasHfArtifactsChange,
  showDivider = true,
  showHasCode = true,
}) => (
  <div
    className="paper-feed-resource-controls"
    role="group"
    aria-label="Resource filters"
  >
    {showDivider && (
      <span className="paper-feed-resource-divider" aria-hidden="true" />
    )}
    <div className="paper-feed-filter-options">
      {showHasCode && (
        <FeedFilterToggle
          checked={hasCode}
          icon={<Icon name="github" size={14} />}
          label="Has code"
          onChange={onHasCodeChange}
        />
      )}
      <FeedFilterToggle
        checked={hasHfArtifacts}
        icon={<HfMonochromeLogo />}
        label="Has artifacts"
        onChange={onHasHfArtifactsChange}
      />
    </div>
  </div>
);
