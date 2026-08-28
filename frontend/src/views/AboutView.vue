<!--
  @ai-purpose: About page — what Nebula is, what it excels at, links out to snakenet.org/GitHub, sign-in identity.
  @ai-context: 2026-08-27: added three highlights alongside the existing six — Certificate storage
    (the new VariableType.CERTIFICATE, see nebula.models.tables/ProjectView.vue), a mention of the
    sibling nebula-cli project (a standalone Go binary that talks to /api/v1/vault/* using a
    project's access key), and a note on OIDC provider flexibility (any standards-compliant provider
    — Authentik, AWS IAM Identity Center, Microsoft Entra ID — works via api/endpoint.py's generic
    JWKS-based RS256 validation, not just Authentik specifically).
  @ai-context: 2026-08-28: added the built-in MCP server highlight (nebula.mcp_server, mounted at
    /mcp by main.py) — placed second, right after the data-model highlight, since it's a flagship
    differentiator the README's own tagline now leads with too, not just another item in an
    alphabetical-ish list.
  @dependencies: vue, shadcn-vue (card, badge), @phosphor-icons/vue
  @version: 3.2.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-28
-->
<script setup>
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { PhArrowSquareOut, PhGithubLogo } from '@phosphor-icons/vue';
import { useAuth } from '../composables/useAuth';

const { state: auth } = useAuth();

const highlights = [
  {
    title: 'Global environments, per-key clarity',
    description:
      'Environments live above any single project, so "production" or "staging" means the same thing everywhere — while every secret still carries its own encrypted value and its own sync settings.',
  },
  {
    title: 'A built-in MCP server',
    description:
      "Nebula ships its own Model Context Protocol server at /mcp — point an MCP-speaking model or agent at it with one or more project access keys and it can read, find, and change secrets, variables, and certificates directly, no separate integration to build.",
  },
  {
    title: 'Live references, not copies',
    description:
      "Point one secret at another, anywhere in the vault, and it always resolves to the source's current value — rotate it once, and every place that references it updates instantly.",
  },
  {
    title: 'Automatic, multi-target GitHub sync',
    description:
      'Push secrets and variables to as many GitHub repositories as you like, automatically on every change — no separate "sync now" step to remember.',
  },
  {
    title: 'Fine-grained sharing',
    description:
      'Share a project as a viewer or an editor with exactly the access each role needs, down to who can reveal a value versus who can change one.',
  },
  {
    title: 'A full audit trail',
    description:
      'Every read, write, and API retrieval is logged — who did what, when, and from where — so nothing happens to a secret without a record.',
  },
  {
    title: 'Automatic rotation',
    description:
      'Give any secret a rotation schedule and it regenerates itself on time, fanning out to every connected repository with no manual intervention.',
  },
  {
    title: 'Certificate storage',
    description:
      "Upload a certificate file — a private key, a PEM chain, anything — and Nebula stores and encrypts it exactly like any other secret. Certificates never auto-renew; overwrite one with a fresh upload to replace it, from the UI or the REST API.",
  },
  {
    title: 'A CLI for your pipelines',
    description:
      'nebula-cli is a small, single-binary command-line client — link a project with its access key and pull secrets, variables, and certificates straight into a deploy script or CI job.',
  },
  {
    title: 'Bring your own identity provider',
    description:
      'Sign in through any standards-compliant OIDC provider — Authentik, AWS IAM Identity Center, Microsoft Entra ID, or your own — instead of being locked into one.',
  },
];
</script>

<template>
  <div class="max-w-2xl mx-auto px-4 py-8 w-full space-y-6">
    <Card>
      <CardContent>
        <div class="flex items-center gap-2 text-xl font-bold mb-4">
          <img src="/favicon.png" alt="" width="28" height="28" class="rounded-md" /> Nebula Vault
        </div>
        <p class="text-muted-foreground text-sm mb-4">
          Nebula is a secrets manager you run yourself: projects hold your secrets and environment
          variables, environments keep production, staging, and everything else cleanly separated,
          and every value is encrypted at rest under a key only you hold.
        </p>
        <p class="text-muted-foreground text-sm mb-4">
          It was built as a free, open-source, self-hosted alternative to commercial secrets
          managers — no per-seat pricing, no vendor lock-in, and no secret ever leaves
          infrastructure you control.
        </p>
        <p class="text-muted-foreground text-sm">
          Source, API reference, and the encryption model are documented in this repository's
          <code class="font-mono">docs/</code> folder.
        </p>
      </CardContent>
    </Card>

    <Card>
      <CardContent>
        <h2 class="text-sm font-semibold mb-4">What makes Nebula special</h2>
        <div class="grid gap-4 sm:grid-cols-2">
          <div v-for="item in highlights" :key="item.title">
            <div class="text-sm font-medium mb-1">{{ item.title }}</div>
            <p class="text-muted-foreground text-xs leading-relaxed">{{ item.description }}</p>
          </div>
        </div>
      </CardContent>
    </Card>

    <Card>
      <CardContent>
        <h2 class="text-sm font-semibold mb-4">Learn more</h2>
        <div class="flex flex-wrap gap-3">
          <a
            href="https://snakenet.org"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
          >
            snakenet.org
            <PhArrowSquareOut :size="14" />
          </a>
          <a
            href="https://github.com/snakenet-org"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
          >
            <PhGithubLogo :size="14" />
            github.com/snakenet-org
            <PhArrowSquareOut :size="14" />
          </a>
        </div>
      </CardContent>
    </Card>

    <Card>
      <CardContent>
        <div class="text-sm">
          <span class="text-muted-foreground">Signed in as</span> {{ auth.session?.user?.name }}
          <Badge v-if="auth.session?.user?.isAdmin" variant="accent" class="ml-2">admin</Badge>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
