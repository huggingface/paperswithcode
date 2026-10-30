import React from "react";

import { formatPageTitle } from "@/lib/latexPlainText";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

const PrivacyView: React.FC = () => {
  useDocumentTitle(formatPageTitle("Privacy Policy"));

  return (
    <article className="page legal-page">
      <header className="legal-header">
        <p className="legal-kicker">Legal</p>
        <h1>Privacy Policy</h1>
        <p className="legal-effective-date">Effective August 11, 2026</p>
      </header>

      <p>
        This Privacy Policy explains how Hugging Face, Inc. (&ldquo;Hugging Face,&rdquo;
        &ldquo;we,&rdquo; or &ldquo;us&rdquo;) collects, uses, and shares information when you
        use Papers With Code, including its website, research assistant, APIs, and
        related services (the &ldquo;Service&rdquo;).
      </p>

      <section>
        <h2>1. Information we collect</h2>
        <h3>Information you provide</h3>
        <ul>
          <li>
            <strong>Account information.</strong> If you sign in with Hugging Face, we
            receive account identifiers and profile details needed to authenticate you,
            such as your user ID, username, and avatar. If you request contributor
            access, we also receive and retain the verified email address associated with
            your Hugging Face account so we can review and communicate about your request.
          </li>
          <li>
            <strong>Contributions and preferences.</strong> We collect information you
            submit or save, such as paper submissions and edits, bookmarks, display
            preferences, feedback, and communications with us. Material you submit to a
            public research page may be publicly visible.
          </li>
          <li>
            <strong>Research assistant content.</strong> We collect your questions,
            conversation history, generated answers, citations, tool calls and results,
            and feedback about answers. Chats are private to your account unless you
            choose to create a share link; anyone with that link may be able to view the
            shared chat.
          </li>
          <li>
            <strong>Provider and billing information.</strong> If you enable a model
            provider, we process the authorization or API credentials needed to make
            requests on your behalf. Hugging Face or another provider processes its own
            billing information under its terms. Papers With Code does not collect your
            payment-card details.
          </li>
        </ul>

        <h3>Information collected automatically</h3>
        <p>
          We collect technical and usage information such as IP address, browser and
          device type, operating system, pages or features used, dates and times,
          referring pages, request identifiers, cookies, logs, and diagnostic data. For
          research-assistant requests, this may include the selected model, token and cost
          details, latency, errors, and other operational metadata.
        </p>

        <h3>Research assistant tracing</h3>
        <p>
          To evaluate, debug, secure, and improve the research assistant, we use Langfuse
          to record traces. A trace may contain the complete text of your question and the
          assistant&apos;s answer, as well as tool inputs, tool outputs, retrieved research
          material, model details, usage data, and related operational metadata.
          <strong> This trace content is not redacted before it is sent to Langfuse.</strong>
        </p>
        <p>
          Papers With Code is designed for questions about research literature. Do not
          put passwords, API keys, confidential information, health or financial data, or
          other sensitive personal information in research-assistant prompts.
        </p>
      </section>

      <section>
        <h2>2. How we use information</h2>
        <p>We use information to:</p>
        <ul>
          <li>provide, personalize, maintain, and operate the Service;</li>
          <li>authenticate users and keep accounts and the Service secure;</li>
          <li>run research-assistant requests and preserve conversation history;</li>
          <li>measure performance, troubleshoot failures, and improve quality;</li>
          <li>review contributions, prevent abuse, and enforce applicable terms;</li>
          <li>communicate with you and respond to requests; and</li>
          <li>comply with law and protect users, Hugging Face, and the public.</li>
        </ul>
      </section>

      <section>
        <h2>3. How we share information</h2>
        <p>We may share information in these circumstances:</p>
        <ul>
          <li>
            <strong>Service providers.</strong> Vendors process information for hosting,
            authentication, analytics, observability, security, and support. These include
            Hugging Face services, Langfuse for research-assistant tracing, Plausible for
            website analytics, and infrastructure providers.
          </li>
          <li>
            <strong>Model providers.</strong> Research-assistant content is sent to the
            model provider you use, such as Hugging Face Inference Providers or
            OpenRouter, so it can generate a response. That provider&apos;s privacy terms
            also apply to its processing.
          </li>
          <li>
            <strong>Public and shared content.</strong> Contributions intended for public
            pages are public. A chat is disclosed through the Service when you create and
            distribute a share link.
          </li>
          <li>
            <strong>Legal, safety, and corporate events.</strong> We may disclose
            information when reasonably necessary to comply with law, protect rights and
            safety, investigate abuse, or complete a merger, acquisition, financing, or
            transfer of assets.
          </li>
        </ul>
        <p>We do not sell your personal information.</p>
      </section>

      <section>
        <h2>4. Cookies and analytics</h2>
        <p>
          We use cookies and similar storage when needed for sign-in, security,
          preferences, and operation of the Service. We also use Plausible to understand
          aggregate website usage. You can control cookies through your browser, but
          disabling necessary cookies may prevent account features from working.
        </p>
      </section>

      <section>
        <h2>5. Legal bases</h2>
        <p>
          Where applicable law requires a legal basis, we process information as needed
          to perform our agreement with you, with your consent, to comply with legal
          obligations, and for legitimate interests such as operating, securing, and
          improving the Service. You may withdraw consent where consent is the basis for
          processing, without affecting earlier processing.
        </p>
      </section>

      <section>
        <h2>6. Retention and deletion</h2>
        <p>
          Private chats are retained until you delete them, subject to limits of 500
          active chats and 100 MB of chat data per user. Archiving hides a chat and
          frees active-chat quota but does not delete it. You may deliberately share an
          unlisted snapshot; deleting its private chat removes the durable transcript,
          workspace reference, and share link after deletion is verified. No dedicated
          private-chat export format is currently offered.
        </p>
        <p>
          We keep information for as long as reasonably needed for the purposes described
          here, including providing the Service, maintaining security and audit records,
          resolving disputes, and meeting legal obligations. Retention periods vary by
          data type and service provider. You can delete individual chats in the Service.
          Deletion may not immediately remove information from backups, security logs, or
          third-party systems where limited retention is required.
        </p>
      </section>

      <section>
        <h2>7. Security and international transfers</h2>
        <p>
          We use reasonable administrative, technical, and organizational safeguards, but
          no internet service can guarantee absolute security. We and our service
          providers may process information in the United States and other countries,
          which may have different data-protection laws from your country. Where required,
          we use appropriate safeguards for international transfers.
        </p>
      </section>

      <section>
        <h2>8. Your privacy rights</h2>
        <p>
          Depending on where you live, you may have rights to access, correct, delete, or
          receive a copy of your personal information; object to or restrict processing;
          withdraw consent; or appeal a decision about a request. You may also have the
          right to complain to a data-protection authority. We may need to verify your
          identity before fulfilling a request.
        </p>
      </section>

      <section>
        <h2>9. Children</h2>
        <p>
          The Service is not directed to children under 13, and we do not knowingly
          collect personal information from children under 13. If you believe a child has
          provided personal information, please contact us.
        </p>
      </section>

      <section>
        <h2>10. Changes to this policy</h2>
        <p>
          We may update this policy as the Service changes. We will post the revised
          policy here and update its effective date. If a change is material, we will
          provide additional notice when appropriate.
        </p>
      </section>

      <section>
        <h2>11. Contact us</h2>
        <p>
          For questions or privacy requests, contact{" "}
          <a href="mailto:privacy@huggingface.co">privacy@huggingface.co</a>. Please do
          not include passwords, API keys, or other sensitive credentials in your message.
        </p>
      </section>
    </article>
  );
};

export default PrivacyView;
