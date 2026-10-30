import { assetUrl } from "@/lib/apiUrl";
import type { PendingEditOf } from "@/lib/pendingEdits";
import { DiffColumn, EmptyInline, ExternalLink } from "./shared";

type TaxonomySuggestion = PendingEditOf<
  "new_task" | "new_method" | "new_benchmark" | "new_metric" | "new_conference"
>;

const SUGGESTION_KIND = {
  new_task: "task",
  new_method: "method",
  new_benchmark: "benchmark",
  new_metric: "metric",
  new_conference: "conference",
} as const;

function TextOrEmpty({ text, empty }: { text?: string; empty: string }) {
  return text ? <span className="submission-field-value">{text}</span> : <EmptyInline>{empty}</EmptyInline>;
}

function SuggestedImage({ edit }: { edit: PendingEditOf<"new_task" | "new_method"> }) {
  const { image, image_credit: imageCredit } = edit.proposed_payload;
  const imageUrl = image?.url !== undefined
    ? assetUrl(image.url) ?? ""
    : image?.data_url?.startsWith("data:image/") ? image.data_url : "";
  return (
    <>
      <DiffColumn title="Image">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={image?.file_name ?? "Suggested image"}
            className="max-h-64 max-w-full rounded-md border border-border object-contain"
          />
        ) : (
          <EmptyInline>No image provided</EmptyInline>
        )}
      </DiffColumn>
      <DiffColumn title="Image source">
        {imageCredit || <EmptyInline>No image source provided</EmptyInline>}
      </DiffColumn>
    </>
  );
}

function KindSpecificFields({ edit }: { edit: TaxonomySuggestion }) {
  switch (edit.edit_type) {
    case "new_task": {
      const { parent_id, area_id, keywords } = edit.proposed_payload;
      return (
        <>
          <SuggestedImage edit={edit} />
          <DiffColumn title="Placement and keywords">
            <span className="submission-field-value">
              {JSON.stringify({ parent_id: parent_id ?? null, area_id: area_id ?? null, keywords: keywords ?? null })}
            </span>
          </DiffColumn>
        </>
      );
    }
    case "new_method": {
      const source = edit.proposed_payload.source_url ?? "";
      return (
        <>
          <SuggestedImage edit={edit} />
          <DiffColumn title="Source">
            {/^https?:\/\//.test(source) ? (
              <ExternalLink url={source} />
            ) : (
              <TextOrEmpty text={source} empty="No source provided" />
            )}
          </DiffColumn>
        </>
      );
    }
    case "new_benchmark": {
      const payload = edit.proposed_payload;
      return (
        <DiffColumn title="Task">
          <span className="submission-field-value">
            {"task" in payload ? payload.task : JSON.stringify(payload.task_ids)}
          </span>
        </DiffColumn>
      );
    }
    case "new_metric": {
      const { direction, scale, task_id, dataset_id } = edit.proposed_payload;
      return (
        <DiffColumn title="Metric and leaderboard definition">
          <span className="submission-field-value">
            {JSON.stringify({ direction, scale, task_id, dataset_id })}
          </span>
        </DiffColumn>
      );
    }
    case "new_conference": {
      const { year, start_date: startDate, end_date: endDate, venue, url } = edit.proposed_payload;
      return (
        <>
          <DiffColumn title="Edition and dates">
            {year ? `${year}${startDate ? ` · ${startDate}${endDate ? ` – ${endDate}` : ""}` : ""}` : <EmptyInline>No edition provided</EmptyInline>}
          </DiffColumn>
          <DiffColumn title="Venue">
            {venue || <EmptyInline>No venue provided</EmptyInline>}
          </DiffColumn>
          <DiffColumn title="URL">
            <ExternalLink url={url} empty="No URL provided" />
          </DiffColumn>
        </>
      );
    }
  }
}

export function TaxonomySuggestionDiff({ edit }: { edit: TaxonomySuggestion }) {
  const payload = edit.proposed_payload;
  const name = "benchmark" in payload ? payload.benchmark : payload.name;

  return (
    <div className="submission-diff-columns">
      <DiffColumn title={`Suggested ${SUGGESTION_KIND[edit.edit_type]} name`}>
        {name ? (
          <span className="submission-diff-pill added">{name}</span>
        ) : (
          <EmptyInline>No name provided</EmptyInline>
        )}
      </DiffColumn>
      <DiffColumn title="Description">
        <TextOrEmpty text={payload.description} empty="No description provided" />
      </DiffColumn>
      <KindSpecificFields edit={edit} />
    </div>
  );
}

export function OrganizationSuggestionDiff({ edit }: { edit: PendingEditOf<"new_organization"> }) {
  const { name, hf_slug: hfSlug, website_url: websiteUrl, image } = edit.proposed_payload;
  const logoUrl = image?.url
    ? assetUrl(image.url)
    : image?.data_url?.startsWith("data:image/")
      ? image.data_url
      : undefined;

  return (
    <div className="submission-diff-columns">
      <DiffColumn title="Suggested organization name">
        <span className="submission-diff-pill added">{name}</span>
      </DiffColumn>
      <DiffColumn title="Hugging Face organization">
        <ExternalLink url={hfSlug ? `https://huggingface.co/${hfSlug}` : undefined} empty="No Hugging Face organization provided" />
      </DiffColumn>
      <DiffColumn title="Website">
        <ExternalLink url={websiteUrl} empty="No website provided" />
      </DiffColumn>
      <DiffColumn title="Logo">
        {logoUrl ? (
          <img
            src={logoUrl}
            alt={image?.file_name ?? "Suggested logo"}
            className="max-h-32 max-w-full rounded-md border border-border object-contain"
          />
        ) : (
          <EmptyInline>No logo provided</EmptyInline>
        )}
      </DiffColumn>
    </div>
  );
}

export function ExternalPaperSuggestionDiff({ edit }: { edit: PendingEditOf<"new_external_paper"> }) {
  const { title, source_url: sourceUrl, abstract, date_published: published, authors } = edit.proposed_payload;

  return (
    <div className="submission-diff-columns">
      <DiffColumn title="Title">
        <TextOrEmpty text={title} empty="No title provided" />
      </DiffColumn>
      <DiffColumn title="Publication date">
        {published || <EmptyInline>No publication date provided</EmptyInline>}
      </DiffColumn>
      <DiffColumn title="Authors">
        {authors.length > 0 ? (
          authors.map((author, index) => (
            <span key={`${author}-${index}`} className="submission-diff-pill added">
              {author}
            </span>
          ))
        ) : (
          <EmptyInline>No authors provided</EmptyInline>
        )}
      </DiffColumn>
      <DiffColumn title="Source URL">
        <ExternalLink url={sourceUrl} empty="No source URL provided" />
      </DiffColumn>
      <DiffColumn title="Abstract">
        <TextOrEmpty text={abstract} empty="No abstract provided" />
      </DiffColumn>
    </div>
  );
}
