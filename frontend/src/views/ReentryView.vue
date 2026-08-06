<!--
  @ai-purpose: OIDC redirect target (/reentry) — completes the Authentik sign-in and signs the user in.
  @ai-context: The "Sign in with snakeNet ID" flow redirects the browser back to /reentry with the
    authorization code. This view runs the token exchange (services/oidc.completeLogin) and the
    Nebula-session handoff (useAuth.loginWithOidc) on mount, showing a spinner while it works. On
    success App.vue swaps in the authenticated shell; on failure or a stale visit it surfaces the
    error and bails back to the login screen via the `done` event. Built from shadcn-vue Card/Button;
    the spinner is a Phosphor icon + Tailwind's `animate-spin`, no bespoke keyframes needed.
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, button)
  @version: 2.0.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-06
-->
<script setup>
import { onMounted, ref } from 'vue';
import { toast } from 'vue-sonner';
import { PhCircleNotch } from '@phosphor-icons/vue';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useAuth } from '../composables/useAuth';
import * as oidc from '../services/oidc';

const emit = defineEmits(['done']);
const { loginWithOidc } = useAuth();
const failed = ref(false);

function leave() {
  oidc.clearCallbackParams();
  history.replaceState(history.state, '', '/');
  emit('done');
}

onMounted(async () => {
  const authErr = oidc.callbackError();
  if (authErr) {
    failed.value = true;
    toast.error(authErr);
    return;
  }

  if (!oidc.isCallback()) {
    leave();
    return;
  }

  try {
    const tokens = await oidc.completeLogin();
    await loginWithOidc(tokens);
    oidc.clearCallbackParams();
    history.replaceState(history.state, '', '/');
  } catch (e) {
    failed.value = true;
    toast.error(e.message || 'Single sign-on failed.');
  }
});
</script>

<template>
  <div class="flex-1 flex items-center justify-center p-4">
    <Card class="w-full max-w-sm">
      <CardContent class="px-8 text-center">
        <div class="flex items-center justify-center gap-2 text-2xl font-bold mb-5">
          <img src="/favicon.svg" alt="" width="26" height="26" class="rounded-md" /> Nebula Vault
        </div>

        <template v-if="!failed">
          <PhCircleNotch :size="40" weight="bold" class="mx-auto animate-spin text-primary" />
          <p class="font-semibold mt-4">Completing sign-in…</p>
          <p class="text-muted-foreground text-sm mt-1">Charting a course back through the nebula.</p>
        </template>

        <template v-else>
          <p class="font-semibold text-destructive">Single sign-on failed</p>
          <Button variant="outline" class="mt-5" @click="leave">Back to login</Button>
        </template>
      </CardContent>
    </Card>
  </div>
</template>
