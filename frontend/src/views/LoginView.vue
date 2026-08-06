<!--
  @ai-purpose: Login screen — local username/password (the optional admin login) + "Sign in with
    snakeNet ID".
  @ai-context: Posts credentials via useAuth.loginLocal, or starts the Authentik PKCE redirect via
    services/oidc.beginLogin. The basic form is shown only when !config.basicLoginDisabled; the OIDC
    button is shown only when OIDC.enabled and its caption comes from OIDC.caption. A pure-CSS
    animated backdrop renders drifting light-blue/yellow nebula wisps over a twinkling starfield —
    this app's palette (see style.css's header comment) — honours prefers-reduced-motion. Built from
    shadcn-vue Card/Input/Label/Button.
  @dependencies: vue, vue-sonner, shadcn-vue (card, input, label, button)
  @version: 2.0.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-06
-->
<script setup>
import { ref } from 'vue';
import { toast } from 'vue-sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { useAuth } from '../composables/useAuth';
import { useConfig } from '../composables/useConfig';
import { OIDC } from '../config/oidc';
import { beginLogin } from '../services/oidc';

const { loginLocal } = useAuth();
const { state: config } = useConfig();

const username = ref('');
const password = ref('');
const busy = ref(false);

async function submit() {
  busy.value = true;
  try {
    await loginLocal(username.value, password.value);
  } catch (e) {
    toast.error(e.message);
  } finally {
    busy.value = false;
  }
}

async function oidcLogin() {
  try {
    const p = window.location.pathname;
    if (p && p !== '/reentry') {
      sessionStorage.setItem('nebular.returnPath', p);
    }
    await beginLogin();
  } catch (e) {
    toast.error(e.message);
  }
}
</script>

<template>
  <div class="flex-1 flex items-center justify-center p-4 login-scene">
    <div class="space" aria-hidden="true">
      <div class="stars"></div>
      <div class="wisp wisp-blue"></div>
      <div class="wisp wisp-yellow"></div>
      <div class="wisp wisp-blue-2"></div>
    </div>

    <Card class="w-full max-w-sm relative z-10">
      <CardContent class="px-8">
        <div class="mb-7">
          <h1 class="text-2xl font-bold flex items-center gap-2">
            <img src="/favicon.svg" alt="" width="26" height="26" class="rounded-md" /> Nebular Vault
          </h1>
          <p class="text-muted-foreground text-sm mt-1">A self-hosted secrets manager for snakeNet.org</p>
        </div>

        <form v-if="!config.config.basicLoginDisabled" @submit.prevent="submit" class="space-y-3">
          <div class="space-y-1.5">
            <Label for="login-username">Username</Label>
            <Input id="login-username" v-model="username" placeholder="Username" autocomplete="username" />
          </div>
          <div class="space-y-1.5">
            <Label for="login-password">Password</Label>
            <Input
              id="login-password"
              v-model="password"
              type="password"
              placeholder="Password"
              autocomplete="current-password"
            />
          </div>
          <Button class="w-full" :disabled="busy" type="submit">
            {{ busy ? 'Signing in…' : 'Sign in' }}
          </Button>
        </form>

        <template v-if="OIDC.enabled">
          <div v-if="!config.config.basicLoginDisabled" class="flex items-center gap-3 my-5 text-xs text-muted-foreground">
            <span class="flex-1 border-t border-border"></span>
            or
            <span class="flex-1 border-t border-border"></span>
          </div>
          <Button variant="outline" class="w-full" @click="oidcLogin">{{ OIDC.caption }}</Button>
        </template>
      </CardContent>
    </Card>
  </div>
</template>

<style scoped>
.login-scene {
  position: relative;
  overflow: hidden;
}

.space {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background: radial-gradient(140% 90% at 50% 50%, #0a0f16 0%, #05070c 60%, #030406 100%);
}

.stars {
  position: absolute;
  inset: 0;
  background-image:
    radial-gradient(1px 1px at 10% 15%, #fff, transparent),
    radial-gradient(1px 1px at 24% 44%, rgba(255, 255, 255, 0.8), transparent),
    radial-gradient(1.5px 1.5px at 40% 10%, #fff, transparent),
    radial-gradient(1px 1px at 56% 32%, rgba(255, 255, 255, 0.7), transparent),
    radial-gradient(1px 1px at 70% 18%, #fff, transparent),
    radial-gradient(1.5px 1.5px at 82% 40%, rgba(255, 255, 255, 0.9), transparent),
    radial-gradient(1px 1px at 90% 8%, #fff, transparent),
    radial-gradient(1px 1px at 6% 60%, rgba(255, 255, 255, 0.6), transparent),
    radial-gradient(1px 1px at 33% 66%, #fff, transparent),
    radial-gradient(1px 1px at 62% 74%, rgba(255, 255, 255, 0.7), transparent),
    radial-gradient(1px 1px at 88% 82%, #fff, transparent);
  animation: twinkle 7s ease-in-out infinite;
}

@keyframes twinkle {
  0%, 100% { opacity: 0.55; }
  50% { opacity: 1; }
}

/* ── Nebula wisps — soft drifting blobs in the theme's light-blue/yellow palette ─── */
.wisp {
  position: absolute;
  border-radius: 50%;
  filter: blur(30px);
  mix-blend-mode: screen;
  opacity: 0.55;
}
.wisp-blue {
  left: 12%;
  top: 20%;
  width: 46vmin;
  height: 40vmin;
  background: radial-gradient(circle, rgba(111, 208, 255, 0.55) 0%, transparent 70%);
  animation: drift-a 22s ease-in-out infinite;
}
.wisp-yellow {
  right: 8%;
  bottom: 10%;
  width: 50vmin;
  height: 44vmin;
  background: radial-gradient(circle, rgba(250, 204, 21, 0.4) 0%, transparent 70%);
  animation: drift-b 26s ease-in-out infinite;
}
.wisp-blue-2 {
  right: 22%;
  top: 5%;
  width: 30vmin;
  height: 26vmin;
  background: radial-gradient(circle, rgba(111, 208, 255, 0.3) 0%, transparent 70%);
  animation: drift-c 30s ease-in-out infinite;
}

@keyframes drift-a {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(4vmin, -3vmin) scale(1.08); }
}
@keyframes drift-b {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(-5vmin, 3vmin) scale(1.05); }
}
@keyframes drift-c {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(-3vmin, 4vmin) scale(1.1); }
}

@media (prefers-reduced-motion: reduce) {
  .stars,
  .wisp {
    animation: none;
  }
}
</style>
