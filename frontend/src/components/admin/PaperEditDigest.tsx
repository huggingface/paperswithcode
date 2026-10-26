import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { paperEditsApi } from "@/lib/api/paperEdits";

export function PaperEditDigest() {
  const [day, setDay] = useState(() => new Date().toISOString().slice(0, 10));
  const [page, setPage] = useState(1);
  const query = useQuery({ queryKey: ["paper-edit-digest", day, page], queryFn: () => paperEditsApi.digest(day, page), enabled: Boolean(day) });
  return <section className="space-y-3 rounded border p-4">
    <h2 className="text-lg font-semibold">Daily paper edits</h2>
    <label className="flex items-center gap-2">UTC date <input type="date" value={day} onChange={e => { setDay(e.target.value); setPage(1); }} /></label>
    {query.isLoading && <p>Loading daily summary…</p>}
    {query.error && <p role="alert">{query.error.message}</p>}
    {query.data && <>
      <p>{query.data.edits} published changes · {query.data.papers} papers · {query.data.contributors} contributors</p>
      <ul className="space-y-1">{query.data.rows.map((row, index) => <li key={index}>
        <Link className="underline" to={`/paper/${row.paper_id}`}>Paper {row.paper_id}</Link> · @{row.actor_username ?? "admin"} · {row.edits} changes
      </li>)}</ul>
      <div className="flex gap-2">
        {page > 1 && <Button variant="outline" onClick={() => setPage(page - 1)}>Previous</Button>}
        {query.data.has_more && <Button variant="outline" onClick={() => setPage(page + 1)}>Next</Button>}
      </div>
    </>}
  </section>;
}
