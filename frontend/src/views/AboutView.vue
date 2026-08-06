<!--
  @ai-purpose: About page — what Nebula Vault is, a link back to the docs, sign-in identity.
  @dependencies: vue, shadcn-vue (card, badge)
  @version: 2.0.1
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-06
-->
<script setup>
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useAuth } from '../composables/useAuth';

const { state: auth } = useAuth();
</script>

<template>
  <div class="max-w-2xl mx-auto px-4 py-8 w-full">
    <Card>
      <CardContent>
        <div class="flex items-center gap-2 text-xl font-bold mb-4">
          <img src="/favicon.png" alt="" width="28" height="28" class="rounded-md" /> Nebula Vault
        </div>
        <p class="text-muted-foreground text-sm mb-4">
          A self-hosted secrets manager for snakeNet.org — Projects hold Environments, each Environment
          can carry its own value for every secret Key, and every value is encrypted at rest under an
          operator-supplied master key.
        </p>
        <p class="text-muted-foreground text-sm mb-6">
          Source, API reference, and the encryption model are documented in this repository's
          <code class="font-mono">docs/</code> folder.
        </p>
        <div class="text-sm">
          <span class="text-muted-foreground">Signed in as</span> {{ auth.session?.user?.name }}
          <Badge v-if="auth.session?.user?.isAdmin" variant="accent" class="ml-2">admin</Badge>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
