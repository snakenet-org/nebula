<!--
  @ai-purpose: Header "Generate password" modal — UUID v4 or a random secure password, either way
    copy-to-clipboard.
  @ai-context: Controlled dialog (`open`/`update:open`, same pattern App.vue already uses for every
    other overlay). Two shadcn-vue Tabs: "UUID v4" regenerates on demand (PhArrowsClockwise); "Secure
    password" has a Slider (10–25 chars, nebula.lib.generators' PASSWORD_MIN/MAX_LENGTH) that
    regenerates a fresh password on every step per the product ask ("with each step of the slider the
    password should randomly generate new"), plus its own explicit regenerate button. Both values are
    shown in a monospace read-only box with a Copy button (PhCopy/PhCheck swap, same 1500ms-then-
    revert pattern as ProjectSettingsView's access-token copy button) plus a `toast.success` (vue-sonner,
    same convention as every other mutation toast in the app) so the click is unmistakable even though
    the icon-swap alone sits inside a small icon button. Nothing here ever leaves the browser — no API
    call, no persistence.
  @dependencies: vue, @phosphor-icons/vue, vue-sonner, shadcn-vue (dialog, tabs, slider, button)
  @version: 1.1.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-08
-->
<script setup>
import { ref, watch } from 'vue';
import { PhArrowsClockwise, PhCheck, PhCopy } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Slider } from '@/components/ui/slider';
import { Button } from '@/components/ui/button';
import {
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  generateSecurePassword,
  generateUuidV4,
} from '../lib/generators';

const props = defineProps({ open: { type: Boolean, default: false } });
const emit = defineEmits(['update:open']);

const uuid = ref(generateUuidV4());
const passwordLength = ref([16]);
const password = ref(generateSecurePassword(passwordLength.value[0]));

function newUuid() {
  uuid.value = generateUuidV4();
}
function newPassword() {
  password.value = generateSecurePassword(passwordLength.value[0]);
}
watch(passwordLength, () => newPassword());

// Fresh values each time the dialog opens.
watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      newUuid();
      newPassword();
    }
  }
);

const copiedUuid = ref(false);
const copiedPassword = ref(false);
function copy(value, flag) {
  navigator.clipboard?.writeText(value);
  flag.value = true;
  toast.success('Copied to clipboard.');
  setTimeout(() => (flag.value = false), 1500);
}
</script>

<template>
  <Dialog :open="open" @update:open="(v) => emit('update:open', v)">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>Generate password</DialogTitle>
        <DialogDescription>Nothing here is sent anywhere — generated locally in your browser.</DialogDescription>
      </DialogHeader>

      <Tabs default-value="uuid">
        <TabsList class="w-full">
          <TabsTrigger value="uuid" class="flex-1">UUID v4</TabsTrigger>
          <TabsTrigger value="password" class="flex-1">Secure password</TabsTrigger>
        </TabsList>

        <TabsContent value="uuid" class="space-y-3 pt-2">
          <div class="flex items-center gap-2">
            <code class="font-mono text-sm flex-1 break-all bg-muted rounded-md px-3 py-2">{{ uuid }}</code>
            <Button variant="outline" size="icon" title="Generate new" @click="newUuid">
              <PhArrowsClockwise :size="16" weight="bold" />
            </Button>
            <Button variant="outline" size="icon" title="Copy" @click="copy(uuid, copiedUuid)">
              <PhCheck v-if="copiedUuid" :size="16" weight="bold" />
              <PhCopy v-else :size="16" weight="bold" />
            </Button>
          </div>
        </TabsContent>

        <TabsContent value="password" class="space-y-4 pt-2">
          <div class="flex items-center gap-2">
            <code class="font-mono text-sm flex-1 break-all bg-muted rounded-md px-3 py-2">{{ password }}</code>
            <Button variant="outline" size="icon" title="Generate new" @click="newPassword">
              <PhArrowsClockwise :size="16" weight="bold" />
            </Button>
            <Button variant="outline" size="icon" title="Copy" @click="copy(password, copiedPassword)">
              <PhCheck v-if="copiedPassword" :size="16" weight="bold" />
              <PhCopy v-else :size="16" weight="bold" />
            </Button>
          </div>
          <div class="space-y-2">
            <div class="flex items-center justify-between text-xs text-muted-foreground">
              <span>Length</span>
              <span>{{ passwordLength[0] }} characters</span>
            </div>
            <Slider
              v-model="passwordLength"
              :min="PASSWORD_MIN_LENGTH"
              :max="PASSWORD_MAX_LENGTH"
              :step="1"
            />
          </div>
          <p class="text-xs text-muted-foreground">
            Letters (a–z, A–Z), numbers (0–9), and hyphens.
          </p>
        </TabsContent>
      </Tabs>
    </DialogContent>
  </Dialog>
</template>
