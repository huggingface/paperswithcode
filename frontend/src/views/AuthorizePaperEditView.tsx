import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import HfSignInButton from "@/components/HfSignInButton";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/authContext";
import { paperEditsApi } from "@/lib/api/paperEdits";

export default function AuthorizePaperEditView() {
  const { authorizationId = "" } = useParams();
  const { user, isLoading } = useAuth();
  const query = useQuery({ queryKey: ["paper-edit-authorization", authorizationId], queryFn: () => paperEditsApi.authorization(authorizationId), retry: false });
  const approval = useMutation({ mutationFn: () => paperEditsApi.approve(authorizationId) });
  const grant = query.data;
  return <main className="mx-auto max-w-xl space-y-5 px-6 py-12">
    <h1 className="text-2xl font-semibold">Authorize your agent to edit a paper</h1>
    {(query.isLoading || isLoading) && <p>Loading authorization…</p>}
    {query.error && <p role="alert">{query.error.message}</p>}
    {grant && <>
      <Link className="underline" to={`/paper/${grant.paper_id}`}>{grant.title}</Link>
      <p>Check that your CLI shows this code: <strong className="font-mono">{grant.user_code}</strong></p>
      <p>Only approve a request you started. Your agent will be able to publish changes to this paper’s links, tags, and evaluation results for one hour, without further approval.</p>
      <p>Edits appear publicly under your Hugging Face username. You can edit up to 20 distinct papers per UTC day. Evaluation deletion and changes to shared benchmark definitions require an administrator.</p>
      {approval.isSuccess || grant.approved ? <p role="status">Access approved. Return to your CLI to continue.</p> : user ? <>
        <p>Signed in as <strong>@{user.username}</strong></p>
        <Button disabled={approval.isPending || !user.can_directly_edit_catalog} onClick={() => approval.mutate()}>
          {approval.isPending ? "Authorizing…" : "Authorize for one hour"}
        </Button>
        {!user.can_directly_edit_catalog && <p>Direct editing is unavailable for this session.</p>}
      </> : <HfSignInButton returnTo={`/authorize-paper-edit/${authorizationId}`} label="Sign in with Hugging Face" />}
      {approval.error && <p role="alert">{approval.error.message}</p>}
    </>}
  </main>;
}
