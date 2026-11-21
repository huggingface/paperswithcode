import { useEffect, useState, type ComponentType } from "react";
import ReactMarkdown from "react-markdown";
import { useQuery } from "@tanstack/react-query";
import {
  Braces,
  Database,
  FileText,
  Gauge,
  KeyRound,
  ListTree,
  Trophy,
  type LucideProps,
} from "lucide-react";
import {
  codeExample,
  exampleUrl,
  groupByTag,
  publicSpecQuery,
  schemaLabel,
  shortPath,
  type Operation,
  type PublicSpec,
  type Schema,
} from "@/lib/api/publicDocs";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import "./ApiDocsView.css";

const LANGUAGES = ["curl", "Python", "JavaScript"];
const FEEDBACK =
  "https://github.com/huggingface/paperswithcode/issues/new?template=api.yml";

const RESOURCES: Record<
  string,
  { label: string; blurb: string; icon: ComponentType<LucideProps> }
> = {
  papers: {
    label: "Papers",
    blurb: "Search, recent and trending papers, with code and project links.",
    icon: FileText,
  },
  tasks: {
    label: "Tasks",
    blurb: "The research task taxonomy, from image classification to agents.",
    icon: ListTree,
  },
  datasets: {
    label: "Datasets",
    blurb: "Benchmarks and the task and metric pairs that form leaderboards.",
    icon: Database,
  },
  evaluations: {
    label: "Evaluations",
    blurb: "Reported scores tying a paper to a dataset, task, and metric.",
    icon: Trophy,
  },
};

function resource(tag: string) {
  return (
    RESOURCES[tag] ?? {
      label: tag.charAt(0).toUpperCase() + tag.slice(1),
      blurb: "",
      icon: Braces,
    }
  );
}

const LEADERBOARD_STEPS = [
  { title: "Find a dataset", path: "/api/v1/datasets/", query: "?q=ImageNet" },
  {
    title: "List its tasks",
    path: "/api/v1/datasets/{dataset_id}/tasks/",
    query: "",
  },
  {
    title: "Pick a metric",
    path: "/api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics",
    query: "",
  },
  {
    title: "Rank evaluations",
    path: "/api/v1/evaluations/",
    query: "?dataset_id=…&task_id=…&ordering=best_rank",
  },
];

const ERRORS = [
  { status: "400", tone: "warn", text: "Invalid request." },
  { status: "404", tone: "warn", text: "Record not found." },
  {
    status: "422",
    tone: "warn",
    text: "Invalid parameter type, value, or missing parameter.",
  },
  {
    status: "429",
    tone: "limit",
    text: (
      <>
        Traffic limit exceeded; obey <code>Retry-After</code>.
      </>
    ),
  },
  {
    status: "5xx",
    tone: "error",
    text: "Temporary server failure; retry with bounded backoff.",
  },
];

function Code({ value }: { value: string }) {
  const [status, setStatus] = useState("Copy");
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setStatus("Copied");
    } catch {
      setStatus("Select and copy the code below");
    }
  }
  return (
    <div className="api-code">
      <pre>
        <code>{value}</code>
      </pre>
      <button onClick={copy} aria-live="polite">
        {status}
      </button>
    </div>
  );
}

function Method() {
  return <span className="api-method">GET</span>;
}

function SchemaDetails({ schema }: { schema: Schema }) {
  if (schema.$ref) {
    const name = schemaLabel(schema);
    return <a href={`#model-${name}`}>{name}</a>;
  }
  if (schema.anyOf || schema.allOf)
    return (
      <>
        {(schema.anyOf ?? schema.allOf)!.map((part, index) => (
          <span key={index}>
            {index > 0 && " | "}
            <SchemaDetails schema={part} />
          </span>
        ))}
      </>
    );
  if (schema.type === "array")
    return (
      <>
        array of <SchemaDetails schema={schema.items ?? {}} />
      </>
    );
  return <code>{schemaLabel(schema)}</code>;
}

function Constraints({ schema }: { schema: Schema }) {
  return (
    <>
      {(["minimum", "maximum", "minLength", "maxLength"] as const).map(
        (bound) =>
          schema[bound] !== undefined && (
            <small key={bound}>
              {bound}: {schema[bound]}
            </small>
          ),
      )}
      {(schema.anyOf ?? schema.allOf ?? []).map((part, index) => (
        <Constraints key={index} schema={part} />
      ))}
    </>
  );
}

function Fields({ schema }: { schema: Schema }) {
  if (!schema.properties) return <SchemaDetails schema={schema} />;
  return (
    <div className="api-table-wrap">
      <table>
        <thead>
          <tr>
            <th>Field</th>
            <th>Type</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(schema.properties).map(([name, field]) => (
            <tr key={name}>
              <td>
                <code>{name}</code>
                {schema.required?.includes(name) && <small>required</small>}
              </td>
              <td>
                <SchemaDetails schema={field} />
              </td>
              <td>
                {field.description}
                {field.format && <small>Format: {field.format}</small>}
                {field.default !== undefined && (
                  <small>Default: {JSON.stringify(field.default)}</small>
                )}
                {field.properties && <Fields schema={field} />}
                {typeof field.additionalProperties === "object" && (
                  <p>
                    Values:{" "}
                    <SchemaDetails schema={field.additionalProperties} />
                  </p>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Endpoint({ path, operation }: { path: string; operation: Operation }) {
  const [language, setLanguage] = useState("curl");
  const tag = operation.tags?.[0];
  return (
    <section id={operation.operationId} className="api-endpoint">
      {tag && <span className="api-eyebrow">{resource(tag).label}</span>}
      <h2>{operation.summary}</h2>
      <p className="api-path">
        <Method /> <code>{path}</code>
      </p>
      <div className="api-description">
        <ReactMarkdown>{operation.description}</ReactMarkdown>
      </div>
      {!!operation.parameters?.length && (
        <>
          <h3>Parameters</h3>
          <div className="api-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Parameter</th>
                  <th>Type</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {operation.parameters.map((parameter) => (
                  <tr key={`${parameter.in}-${parameter.name}`}>
                    <td>
                      <code>{parameter.name}</code>
                      <small>
                        {parameter.in} ·{" "}
                        {parameter.required ? "required" : "optional"}
                      </small>
                    </td>
                    <td>
                      <SchemaDetails schema={parameter.schema} />
                    </td>
                    <td>
                      {parameter.description}
                      {parameter.schema.default !== undefined && (
                        <small>
                          Default: {JSON.stringify(parameter.schema.default)}
                        </small>
                      )}
                      <Constraints schema={parameter.schema} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <h3>Example request</h3>
      <div
        className="api-languages"
        role="group"
        aria-label={`Example language for ${operation.summary}`}
      >
        {LANGUAGES.map((value) => (
          <button
            key={value}
            aria-pressed={language === value}
            onClick={() => setLanguage(value)}
          >
            {value}
          </button>
        ))}
      </div>
      <Code value={codeExample(exampleUrl(path, operation), language)} />
      <h3>Responses</h3>
      {Object.entries(operation.responses).map(([status, response]) => (
        <div className="api-response" key={status}>
          <span className={`api-status api-status-${status[0]}`}>{status}</span>{" "}
          {response.description}
          {response.content?.["application/json"]?.schema && (
            <>
              {" "}
              →{" "}
              <SchemaDetails
                schema={response.content["application/json"].schema!}
              />
            </>
          )}
        </div>
      ))}
    </section>
  );
}

function ResourceMap({ spec }: { spec: PublicSpec }) {
  return (
    <div className="api-resources">
      {groupByTag(spec.paths).map(([tag, entries]) => {
        const { label, blurb, icon: Icon } = resource(tag);
        return (
          <article key={tag} className="api-resource">
            <header>
              <span className="api-resource-icon" aria-hidden="true">
                <Icon size={18} />
              </span>
              <h3>{label}</h3>
            </header>
            {blurb && <p>{blurb}</p>}
            <ul>
              {entries.map(({ path, operation }) => (
                <li key={path}>
                  <a href={`#${operation.operationId}`} title={operation.summary}>
                    <Method />
                    <code>{shortPath(path)}</code>
                  </a>
                </li>
              ))}
            </ul>
          </article>
        );
      })}
    </div>
  );
}

function openHashTarget() {
  const target = window.location.hash
    ? document.getElementById(decodeURIComponent(window.location.hash.slice(1)))
    : null;
  if (!target) return;
  const details = target.closest("details");
  if (details) details.open = true;
  target.scrollIntoView();
}

export default function ApiDocsView() {
  const { data, isPending, isError, refetch } = useQuery(publicSpecQuery);
  useDocumentTitle("API documentation — Papers With Code", { restorePrevious: true });
  useEffect(() => {
    if (!data) return;
    const frame = requestAnimationFrame(openHashTarget);
    window.addEventListener("hashchange", openHashTarget);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("hashchange", openHashTarget);
    };
  }, [data]);
  const groups = data ? groupByTag(data.paths) : [];
  const endpointCount = data ? Object.keys(data.paths).length : null;
  return (
    <div className="api-docs">
      <nav className="api-sidebar" aria-label="API documentation">
        <strong>API documentation</strong>
        <div className="api-sidebar-group">
          <span>Guides</span>
          <a href="#getting-started">Getting started</a>
          <a href="#overview">Catalog overview</a>
          <a href="#limits">Traffic limits</a>
          <a href="#pagination">Pagination & identifiers</a>
          <a href="#benchmarks">Reading leaderboards</a>
          <a href="#errors">Errors</a>
          <a href="#changelog">Changelog</a>
        </div>
        {groups.map(([tag, entries]) => (
          <div key={tag} className="api-sidebar-group">
            <span>{resource(tag).label}</span>
            {entries.map(({ path, operation }) => (
              <a key={path} href={`#${operation.operationId}`}>
                <Method />
                {operation.summary}
              </a>
            ))}
          </div>
        ))}
        <div className="api-sidebar-group">
          <span>Reference</span>
          <a href="#response-models">Response models</a>
        </div>
      </nav>
      <div className="api-content">
        <section id="getting-started" className="api-hero">
          <span className="api-beta">Experimental beta</span>
          <h1>Papers With Code API</h1>
          <p className="api-lead">
            Find papers, explore benchmarks, and bring research results into
            your scripts and applications.
          </p>
          <div className="api-facts">
            <div>
              <KeyRound size={18} aria-hidden="true" />
              <b>No API key</b>
              <span>Free, anonymous, read-only access</span>
            </div>
            <div>
              <Gauge size={18} aria-hidden="true" />
              <b>120 / minute</b>
              <span>Per IP, with short bursts</span>
            </div>
            <div>
              <Braces size={18} aria-hidden="true" />
              <b>
                {endpointCount === null
                  ? "OpenAPI"
                  : `${endpointCount} endpoints`}
              </b>
              <span>JSON responses, OpenAPI schema</span>
            </div>
          </div>
          <p>
            No account or API key required. The public beta covers keyword
            search and core catalog lookups.
          </p>
          <p>
            <a href="https://paperswithcode.co/api/v1/openapi.json">
              Download the public OpenAPI specification
            </a>{" "}
            · <a href={FEEDBACK}>Report a bug or request a feature</a>
          </p>
          <h2>Your first request</h2>
          <div className="api-terminal">
            <div className="api-terminal-bar" aria-hidden="true">
              <i />
              <i />
              <i />
              <span>Terminal</span>
            </div>
            <Code
              value={
                'curl --fail-with-body "https://paperswithcode.co/api/v1/papers/search?q=attention&mode=keyword&page_size=5"'
              }
            />
          </div>
          <p>
            Responses are JSON. Python examples require{" "}
            <code>pip install requests</code>; JavaScript examples use built-in{" "}
            <code>fetch</code>. Browser requests from any origin are supported
            for these public reads: omit cookies and authorization headers.
          </p>
          <p>
            Base URL: <code>https://paperswithcode.co/api/v1</code>
          </p>
        </section>
        <section id="overview">
          <h2>Catalog overview</h2>
          <p>
            Four resources make up the catalog. Evaluations connect them: each
            one is a score a paper reports on a dataset for a task.
          </p>
          {data ? (
            <ResourceMap spec={data} />
          ) : (
            <p className="api-muted">The endpoint overview loads with the reference below.</p>
          )}
        </section>
        <section id="limits">
          <h2>Traffic limits</h2>
          <div className="api-limits">
            <div>
              <b>120</b>
              <span>requests/minute</span>
              <p>All catalog reads · bursts of up to 60 more</p>
            </div>
            <div>
              <b>60</b>
              <span>requests/minute</span>
              <p>List and search endpoints · bursts of up to 20 more</p>
            </div>
          </div>
          <p>
            Each IP address shares a catalog allowance of 120 requests/minute.
            List and search endpoints also share a stricter allowance of 60
            requests/minute. These are sustained rates with short bursts of up
            to 60 and 20 excess requests respectively, not fixed-minute quotas.
          </p>
          <p>
            Website browsing and scripts on the same network share these limits.
            Send requests sequentially, cache results, and avoid parallel
            crawls. On HTTP 429, wait at least the <code>Retry-After</code>{" "}
            duration, then retry with increasing delays and jitter. Browser
            preflight requests do not consume this allowance.
          </p>
        </section>
        <section id="pagination">
          <h2>Pagination & identifiers</h2>
          <p>
            Paginated endpoints return <code>results</code>,{" "}
            <code>next_page</code>, and <code>previous_page</code>. Catalog
            lists also return <code>count</code>; paper search omits it. Pass{" "}
            <code>page</code> and <code>page_size</code>; stop when{" "}
            <code>next_page</code> is null. Recent and trending endpoints
            instead return arrays bounded by <code>limit</code>.
          </p>
          <p>
            Paper listing and search stop at page 100. Other bounds are shown
            per endpoint. Counts and page contents may change as the catalog
            updates; pagination is not a snapshot or a bulk export interface.
          </p>
          <p>
            Use identifiers returned by lookups. Paper detail accepts an arXiv
            ID or numeric catalog ID; the arXiv endpoint takes an arXiv ID. Task
            and dataset detail accept their catalog IDs or slugs. Leaderboard
            metrics require numeric task and dataset IDs. Evaluation filters
            such as <code>dataset_id</code> and <code>task_id</code> require
            numeric catalog IDs. Example IDs may no longer exist: replace them
            with current lookup results.
          </p>
        </section>
        <section id="benchmarks">
          <h2>Reading leaderboards</h2>
          <ol className="api-steps">
            {LEADERBOARD_STEPS.map((step, index) => {
              const operationId = data?.paths[step.path]?.get.operationId;
              const label = (
                <code>
                  {shortPath(step.path)}
                  {step.query}
                </code>
              );
              return (
                <li key={step.path}>
                  <span className="api-step-number" aria-hidden="true">
                    {index + 1}
                  </span>
                  <b>{step.title}</b>
                  {operationId ? <a href={`#${operationId}`}>{label}</a> : label}
                </li>
              );
            })}
          </ol>
          <p>
            Search datasets, select a dataset, then fetch its tasks and the
            metrics for a dataset/task pair. Fetch{" "}
            <code>/evaluations/?dataset_id=…&task_id=…&ordering=best_rank</code>{" "}
            using the numeric IDs. An evaluation includes reported scores and
            source information; check metric direction, split, and evaluation
            setup before comparing results.
          </p>
          <p>
            Use <code>include_resources=true</code> on paper list/detail
            requests for linked repositories and project pages. Missing fields
            or null values mean data is unavailable; they are not zero scores.
            Keyword search examples explicitly send <code>mode=keyword</code>;
            semantic and hybrid search are outside this beta.
          </p>
        </section>
        <section id="errors">
          <h2>Errors</h2>
          <p>
            Check the HTTP status before parsing a successful result. Errors
            usually contain a <code>detail</code> field, which can be a string,
            object, or validation-error array.
          </p>
          <ul className="api-errors">
            {ERRORS.map(({ status, tone, text }) => (
              <li key={status}>
                <span className={`api-status api-status-${tone}`}>{status}</span>
                <span>{text}</span>
              </li>
            ))}
          </ul>
          <Code
            value={
              '{ "detail": "API traffic limit exceeded. Retry with backoff." }'
            }
          />
        </section>
        <section id="changelog">
          <h2>Changelog</h2>
          <h3>Initial experimental beta</h3>
          <p>
            Core catalog reads, keyword search, public schemas, and anonymous
            browser access. Planned breaking changes will be announced here at
            least 14 days before they take effect. Urgent security and
            service-restoration fixes may take effect immediately. This beta has
            no uptime or support-response guarantee.
          </p>
        </section>
        {isPending && <p role="status">Loading endpoint reference…</p>}
        {isError && (
          <div role="alert">
            <p>Could not load the endpoint reference.</p>
            <button onClick={() => void refetch()}>Retry</button>
          </div>
        )}
        {data && (
          <>
            {Object.entries(data.paths).map(([path, { get }]) => (
              <Endpoint key={path} path={path} operation={get} />
            ))}
            <section id="response-models">
              <h2>Response models</h2>
              <p className="api-muted">
                Expand a model to see its fields. Type links jump to the model.
              </p>
              {Object.entries(data.components.schemas).map(([name, schema]) => (
                <details id={`model-${name}`} key={name} className="api-model">
                  <summary>
                    <code>{name}</code>
                    {schema.description && <span>{schema.description}</span>}
                  </summary>
                  <Fields schema={schema} />
                </details>
              ))}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
