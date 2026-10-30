import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useQuery } from "@tanstack/react-query";
import {
  codeExample,
  exampleUrl,
  publicSpecQuery,
  schemaLabel,
  type Operation,
  type Schema,
} from "@/lib/api/publicDocs";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import "./ApiDocsView.css";

const LANGUAGES = ["curl", "Python", "JavaScript"];
const FEEDBACK =
  "https://github.com/huggingface/paperswithcode/issues/new?template=api.yml";

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
  return (
    <section id={operation.operationId} className="api-endpoint">
      <h2>{operation.summary}</h2>
      <p className="api-path">
        <b>GET</b> <code>{path}</code>
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
          <strong>{status}</strong> {response.description}
          {response.content?.["application/json"]?.schema && (
            <p>
              <SchemaDetails
                schema={response.content["application/json"].schema!}
              />
            </p>
          )}
        </div>
      ))}
    </section>
  );
}

export default function ApiDocsView() {
  const { data, isPending, isError, refetch } = useQuery(publicSpecQuery);
  useDocumentTitle("API documentation — Papers With Code", { restorePrevious: true });
  useEffect(() => {
    if (!data || !window.location.hash) return;
    const frame = requestAnimationFrame(() => {
      document.getElementById(window.location.hash.slice(1))?.scrollIntoView();
    });
    return () => cancelAnimationFrame(frame);
  }, [data]);
  return (
    <div className="api-docs">
      <nav className="api-sidebar" aria-label="API documentation">
        <strong>API documentation</strong>
        <a href="#getting-started">Getting started</a>
        <a href="#limits">Traffic limits</a>
        <a href="#pagination">Pagination & identifiers</a>
        <a href="#benchmarks">Reading leaderboards</a>
        <a href="#errors">Errors</a>
        <a href="#changelog">Changelog</a>
        {data &&
          Object.entries(data.paths).map(([path, { get }]) => (
            <a key={path} href={`#${get.operationId}`}>
              {get.summary}
            </a>
          ))}
        <a href="#response-models">Response models</a>
      </nav>
      <main className="api-content">
        <section id="getting-started">
          <span className="api-beta">Experimental beta</span>
          <h1>Papers With Code API</h1>
          <p className="api-lead">
            Find papers, explore benchmarks, and bring research results into
            your scripts and applications.
          </p>
          <p>
            Free, anonymous, read-only access. No account or API key required.
            The public beta covers keyword search and core catalog lookups.
          </p>
          <p>
            <a href="https://paperswithcode.co/api/v1/openapi.json">
              Download the public OpenAPI specification
            </a>{" "}
            · <a href={FEEDBACK}>Report a bug or request a feature</a>
          </p>
          <h2>Your first request</h2>
          <Code
            value={
              'curl --fail-with-body "https://paperswithcode.co/api/v1/papers/search?q=attention&mode=keyword&page_size=5"'
            }
          />
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
        <section id="limits">
          <h2>Traffic limits</h2>
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
          <ul>
            <li>
              <b>400:</b> invalid request.
            </li>
            <li>
              <b>404:</b> record not found.
            </li>
            <li>
              <b>422:</b> invalid parameter type, value, or missing parameter.
            </li>
            <li>
              <b>429:</b> traffic limit exceeded; obey <code>Retry-After</code>.
            </li>
            <li>
              <b>5xx:</b> temporary server failure; retry with bounded backoff.
            </li>
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
              {Object.entries(data.components.schemas).map(([name, schema]) => (
                <article id={`model-${name}`} key={name}>
                  <h3>{name}</h3>
                  <p>{schema.description}</p>
                  <Fields schema={schema} />
                </article>
              ))}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
