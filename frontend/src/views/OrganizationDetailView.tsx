import React from "react";
import { useParams } from "react-router-dom";

import { OrganizationPaperFeed } from "@/components/OrganizationPaperFeed";
import NotFound from "@/pages/NotFound";

/** Serves both /orgs/:orgSlug and /orgs/:orgSlug/:taskSlug. */
const OrganizationDetailView: React.FC = () => {
  const { orgSlug, taskSlug } = useParams<{ orgSlug: string; taskSlug?: string }>();
  return orgSlug ? <OrganizationPaperFeed organizationSlug={orgSlug} taskSlug={taskSlug} /> : <NotFound />;
};

export default OrganizationDetailView;
