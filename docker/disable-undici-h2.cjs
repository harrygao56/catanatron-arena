const undici = require("/usr/local/lib/node_modules/@earendil-works/pi-coding-agent/node_modules/undici");
undici.setGlobalDispatcher(new undici.Agent({ allowH2: false }));
