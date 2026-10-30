import React from "react";
import { useQuery } from "@tanstack/react-query";

import TrendChart from "@/components/TrendChart";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { statsApi } from "@/lib/api/stats";

const sectionStyle: React.CSSProperties = {
  maxWidth: 960,
  padding: "48px 0 8px",
  borderTop: "1px solid var(--hairline)",
  marginTop: 48,
};

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: "var(--serif)",
  fontSize: 34,
  fontWeight: 500,
  letterSpacing: "-0.02em",
  margin: "0 0 10px",
  color: "var(--ink)",
};

const sectionBlurbStyle: React.CSSProperties = {
  fontFamily: "var(--serif)",
  fontSize: 18,
  lineHeight: 1.55,
  color: "var(--ink-soft)",
  maxWidth: 620,
  margin: "0 0 8px",
};

const methodLabelStyle: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 12,
  fontWeight: 600,
  letterSpacing: "0.14em",
  textTransform: "uppercase",
  color: "var(--ink-faint)",
  marginBottom: 8,
};

const methodTextStyle: React.CSSProperties = {
  fontFamily: "var(--serif)",
  fontSize: 17,
  lineHeight: 1.6,
  color: "var(--ink-soft)",
  margin: 0,
};

const chartSkeletonStyle: React.CSSProperties = {
  height: 320,
  marginTop: 26,
};

const TrendsView: React.FC = () => {
  const trendsQuery = useQuery({
    queryKey: ["research-trends"],
    queryFn: () => statsApi.trends(),
    staleTime: 60 * 60 * 1000,
  });

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            Research <em>Trends</em>
          </h1>
          <div className="feed-subtitle">
            How open science is changing across machine learning — tracked over
            time from arXiv and the Hugging Face Hub.
          </div>
        </div>
      </div>

      {trendsQuery.error && (
        <Alert variant="destructive">
          <AlertDescription>
            Failed to load research trends. Please try again.
          </AlertDescription>
        </Alert>
      )}

      <section style={sectionStyle}>
        <h2 style={sectionTitleStyle}>Code Availability</h2>
        <p style={sectionBlurbStyle}>
          The percentage of published papers that have at least one official
          code implementation on GitHub.
        </p>
        <div style={{ marginTop: 26 }}>
          {trendsQuery.data ? (
            <TrendChart
              id="code"
              data={trendsQuery.data.code_availability}
              color="var(--trend-code)"
              yTicks={[0, 20, 40, 60, 80]}
              yLabel="Code Availability"
              xLabel="Paper Publication Date"
            />
          ) : (
            !trendsQuery.error && <Skeleton style={chartSkeletonStyle} />
          )}
        </div>
      </section>

      <section style={sectionStyle}>
        <h2 style={sectionTitleStyle}>Papers with Hugging Face artifacts</h2>
        <p style={sectionBlurbStyle}>
          The percentage of published papers linked to at least one Hugging
          Face artifact — a model, dataset or Space — making the work directly
          runnable and reusable.
        </p>
        <div style={{ marginTop: 26 }}>
          {trendsQuery.data ? (
            <TrendChart
              id="hf"
              data={trendsQuery.data.hf_artifacts}
              color="var(--trend-hf)"
              yTicks={[0, 10, 20, 30, 40, 50]}
              yLabel="HF Artifact Coverage"
              xLabel="Paper Publication Date"
            />
          ) : (
            !trendsQuery.error && <Skeleton style={chartSkeletonStyle} />
          )}
        </div>
      </section>

      <section style={{ ...sectionStyle, paddingBottom: 72 }}>
        <h2 style={{ ...sectionTitleStyle, fontSize: 27 }}>
          How the data is collected
        </h2>
        <div style={{ display: "grid", gap: 24, maxWidth: 680 }}>
          <div>
            <div style={methodLabelStyle}>Code Availability</div>
            <p style={methodTextStyle}>
              For every open-access machine learning paper, we check whether an
              official code implementation is linked on GitHub. The date axis
              is the paper&apos;s publication date.
            </p>
          </div>
          <div>
            <div style={methodLabelStyle}>Hugging Face artifacts</div>
            <p style={methodTextStyle}>
              We resolve links between papers and the Hugging Face Hub,
              counting a paper as covered when it references at least one
              model, dataset or Space. The date axis is the paper&apos;s
              publication date.
            </p>
          </div>
          <p
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              lineHeight: 1.6,
              color: "var(--ink-faint)",
              margin: "8px 0 0",
              letterSpacing: "0.02em",
            }}
          >
            Figures use complete publication months. Historical Hugging Face
            coverage reflects artifacts currently linked in the catalog.
          </p>
        </div>
      </section>
    </div>
  );
};

export default TrendsView;
