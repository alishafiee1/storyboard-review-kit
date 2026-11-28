/* Entry point of the page: every file is a module; the code that used to run while the scripts loaded now runs here, in the same order, once all modules exist. */
import { S } from './state.js';
import { audio } from './core.js';
import { LA } from './render.js';
import { boot_core } from './core.js';
import { boot_drawer } from './drawer.js';
import { boot_render } from './render.js';
import { boot_versions } from './versions.js';
import { boot_dialogs } from './dialogs.js';
import { boot_prompts } from './prompts.js';
import { boot_panels } from './panels.js';
import { boot_player } from './player.js';
import { boot_gallery } from './gallery.js';
import { boot_flow_panel } from './flow_panel.js';
boot_core();
boot_drawer();
boot_render();
boot_versions();
boot_dialogs();
boot_prompts();
boot_panels();
boot_player();
boot_gallery();
boot_flow_panel();
/* a read-only handle for the browser tests (they wait for the page to finish a reload) */
window.__kit = {
  S,
  audio,
  get LA() { return LA; }
};
window.audio = audio;
Object.defineProperty(window, 'LA', {
  get: () => LA,
  configurable: true
});
