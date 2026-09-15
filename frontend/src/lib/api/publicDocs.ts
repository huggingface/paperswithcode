import { apiRequest } from "./request";

export interface Schema {
  $ref?: string;
  type?: string;
  title?: string;
  description?: string;
  enum?: unknown[];
  default?: unknown;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  format?: string;
  properties?: Record<string, Schema>;
  required?: string[];
  items?: Schema;
  anyOf?: Schema[];
  allOf?: Schema[];
  additionalProperties?: boolean | Schema;
}
export interface Parameter {
  name: string;
  in: string;
  required?: boolean;
  description?: string;
  schema: Schema;
}
export interface Operation {
  operationId: string;
  summary?: string;
  description?: string;
  tags?: string[];
  parameters?: Parameter[];
  responses: Record<
    string,
    { description: string; content?: Record<string, { schema?: Schema }> }
  >;
  "x-example-parameters": Record<string, string | number | boolean>;
}
export interface PublicSpec {
  paths: Record<string, { get: Operation }>;
  components: { schemas: Record<string, Schema> };
}
export const publicSpecQuery = {
  queryKey: ["public-api-schema"],
  queryFn: () =>
    apiRequest<PublicSpec>("/openapi.json", { credentials: "omit" }),
  staleTime: 5 * 60 * 1000,
};

export function exampleUrl(path: string, operation: Operation): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(
    operation["x-example-parameters"],
  )) {
    if (path.includes(`{${key}}`))
      path = path.replace(`{${key}}`, encodeURIComponent(String(value)));
    else query.append(key, String(value));
  }
  return `https://paperswithcode.co${path}${query.size ? `?${query}` : ""}`;
}
export function codeExample(url: string, language: string): string {
  if (language === "Python")
    return `import requests\n\nresponse = requests.get(${JSON.stringify(url)}, timeout=30)\nresponse.raise_for_status()\nprint(response.json())`;
  if (language === "JavaScript")
    return `const response = await fetch(${JSON.stringify(url)}, {\n  credentials: "omit",\n});\nif (!response.ok) throw new Error(\`HTTP \${response.status}\`);\nconsole.log(await response.json());`;
  return `curl --fail-with-body ${JSON.stringify(url)}`;
}
export function schemaLabel(schema: Schema): string {
  if (schema.$ref) return schema.$ref.split("/").pop() ?? "object";
  if (schema.anyOf) return schema.anyOf.map(schemaLabel).join(" | ");
  if (schema.allOf) return schema.allOf.map(schemaLabel).join(" & ");
  if (schema.enum)
    return schema.enum.map((value) => JSON.stringify(value)).join(" | ");
  if (schema.type === "array")
    return `array<${schemaLabel(schema.items ?? {})}>`;
  return schema.type ?? "object";
}
