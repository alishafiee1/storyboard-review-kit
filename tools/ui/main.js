/* Entry point of the page: every file is a module; the code that used to run while the scripts loaded now runs here, in the same order, once all modules exist. */
import { S } from './state.js';
import { boot_paper } from './paper.js';
import { boot_core } from './core.js';
import { boot_render } from './render.js';
import { boot_versions } from './versions.js';
import { boot_dialogs } from './dialogs.js';
import { boot_panels } from './panels.js';
import { boot_player } from './player.js';
boot_paper();
boot_core();
boot_render();
boot_versions();
boot_dialogs();
boot_panels();
boot_player();
/* a read-only handle for the browser tests (they wait for the page to finish a reload) */
window.__kit = { S };
