import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

export const AstraRoboticsFeature: React.FC = () => (
  <Link
    to="/astra-for-robotics"
    className="task-featured-collection"
    aria-label="Featured collection: GPT-6 Astra for Robotics"
  >
    <span className="task-featured-collection-eyebrow">Featured collection</span>
    <strong>GPT-6 Astra for Robotics</strong>
    <span className="task-featured-collection-description">
      Papers and demos that put GPT-6 Astra in control of real and simulated robots, as the
      policy itself or as an agent orchestrating the stack.
    </span>
    <span className="task-featured-collection-meta">
      Explore the collection
      <ArrowRight size={14} aria-hidden="true" />
    </span>
  </Link>
);
