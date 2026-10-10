
  var Module = typeof Module != 'undefined' ? Module : {};

  if (!Module['expectedDataFileDownloads']) Module['expectedDataFileDownloads'] = 0;
  Module['expectedDataFileDownloads']++;
  (() => {
    // Do not attempt to redownload the virtual filesystem data when in a pthread or a Wasm Worker context.
    var isPthread = typeof ENVIRONMENT_IS_PTHREAD != 'undefined' && ENVIRONMENT_IS_PTHREAD;
    var isWasmWorker = typeof ENVIRONMENT_IS_WASM_WORKER != 'undefined' && ENVIRONMENT_IS_WASM_WORKER;
    if (isPthread || isWasmWorker) return;
    async function loadPackage(metadata) {

      var PACKAGE_PATH = '';
      if (typeof window === 'object') {
        PACKAGE_PATH = window['encodeURIComponent'](window.location.pathname.substring(0, window.location.pathname.lastIndexOf('/')) + '/');
      } else if (typeof process === 'undefined' && typeof location !== 'undefined') {
        // web worker
        PACKAGE_PATH = encodeURIComponent(location.pathname.substring(0, location.pathname.lastIndexOf('/')) + '/');
      }
      var PACKAGE_NAME = 'D:/n64work/opennfs/site/assets.data';
      var REMOTE_PACKAGE_BASE = 'assets.data';
      var REMOTE_PACKAGE_NAME = Module['locateFile'] ? Module['locateFile'](REMOTE_PACKAGE_BASE, '') : REMOTE_PACKAGE_BASE;
      var REMOTE_PACKAGE_SIZE = metadata['remote_package_size'];

      async function fetchRemotePackage(packageName, packageSize) {
        
        if (!Module['dataFileDownloads']) Module['dataFileDownloads'] = {};
        try {
          var response = await fetch(packageName);
        } catch (e) {
          throw new Error(`Network Error: ${packageName}`, {e});
        }
        if (!response.ok) {
          throw new Error(`${response.status}: ${response.url}`);
        }

        const chunks = [];
        const headers = response.headers;
        const total = Number(headers.get('Content-Length') || packageSize);
        let loaded = 0;

        Module['setStatus'] && Module['setStatus']('Downloading data...');
        const reader = response.body.getReader();

        while (1) {
          var {done, value} = await reader.read();
          if (done) break;
          chunks.push(value);
          loaded += value.length;
          Module['dataFileDownloads'][packageName] = {loaded, total};

          let totalLoaded = 0;
          let totalSize = 0;

          for (const download of Object.values(Module['dataFileDownloads'])) {
            totalLoaded += download.loaded;
            totalSize += download.total;
          }

          Module['setStatus'] && Module['setStatus'](`Downloading data... (${totalLoaded}/${totalSize})`);
        }

        const packageData = new Uint8Array(chunks.map((c) => c.length).reduce((a, b) => a + b, 0));
        let offset = 0;
        for (const chunk of chunks) {
          packageData.set(chunk, offset);
          offset += chunk.length;
        }
        return packageData.buffer;
      }

      var fetchPromise;
      var fetched = Module['getPreloadedPackage'] && Module['getPreloadedPackage'](REMOTE_PACKAGE_NAME, REMOTE_PACKAGE_SIZE);

      if (!fetched) {
        // Note that we don't use await here because we want to execute the
        // the rest of this function immediately.
        fetchPromise = fetchRemotePackage(REMOTE_PACKAGE_NAME, REMOTE_PACKAGE_SIZE);
      }

    async function runWithFS(Module) {

      function assert(check, msg) {
        if (!check) throw new Error(msg);
      }
Module['FS_createPath']("/", "game", true, true);
Module['FS_createPath']("/game", "resources", true, true);
Module['FS_createPath']("/game/resources", "NFS_3", true, true);
Module['FS_createPath']("/game/resources/NFS_3", "gamedata", true, true);
Module['FS_createPath']("/game/resources/NFS_3/gamedata", "carmodel", true, true);
Module['FS_createPath']("/game/resources/NFS_3/gamedata/carmodel", "cgt1", true, true);
Module['FS_createPath']("/game/resources/NFS_3/gamedata/carmodel", "hat1", true, true);
Module['FS_createPath']("/game/resources/NFS_3/gamedata/carmodel", "traffic", true, true);
Module['FS_createPath']("/game/resources/NFS_3/gamedata/carmodel/traffic", "pursuit", true, true);
Module['FS_createPath']("/game/resources/NFS_3/gamedata/carmodel/traffic/pursuit", "ptl1", true, true);
Module['FS_createPath']("/game/resources/NFS_3/gamedata/carmodel/traffic", "tfc1", true, true);
Module['FS_createPath']("/game/resources/NFS_3/gamedata/carmodel", "wdg1", true, true);
Module['FS_createPath']("/game/resources/NFS_3/gamedata", "render", true, true);
Module['FS_createPath']("/game/resources/NFS_3/gamedata/render", "pc", true, true);
Module['FS_createPath']("/game/resources", "misc", true, true);
Module['FS_createPath']("/game/resources/misc", "sky_textures", true, true);
Module['FS_createPath']("/game/resources/misc", "skydome", true, true);
Module['FS_createPath']("/game/resources", "ui", true, true);
Module['FS_createPath']("/game/resources/ui", "fonts", true, true);
Module['FS_createPath']("/game/resources/ui", "menu", true, true);
Module['FS_createPath']("/game/resources/ui/menu", "images", true, true);
Module['FS_createPath']("/game/resources/ui/menu", "layout", true, true);
Module['FS_createPath']("/game", "shaders", true, true);

      async function processPackageData(arrayBuffer) {
        assert(arrayBuffer, 'Loading data file failed.');
        assert(arrayBuffer.constructor.name === ArrayBuffer.name, 'bad input to processPackageData ' + arrayBuffer.constructor.name);
        var byteArray = new Uint8Array(arrayBuffer);
        var curr;
        // Reuse the bytearray from the XHR as the source for file reads.
          for (var file of metadata['files']) {
            var name = file['filename'];
            var data = byteArray.subarray(file['start'], file['end']);
            // canOwn this data in the filesystem, it is a slice into the heap that will never change
        Module['FS_createDataFile'](name, null, data, true, true, true);
          }
          Module['removeRunDependency']('datafile_D:/n64work/opennfs/site/assets.data');
      }
      Module['addRunDependency']('datafile_D:/n64work/opennfs/site/assets.data');

      if (!Module['preloadResults']) Module['preloadResults'] = {};

      Module['preloadResults'][PACKAGE_NAME] = {fromCache: false};
      if (!fetched) {
        fetched = await fetchPromise;
      }
      await processPackageData(fetched);

    }
    // Detect whether the module JS file has already been loaded.
    if (Module['FS_createPath']) {
      runWithFS(Module);
    } else {
      if (!Module['preRun']) Module['preRun'] = [];
      Module['preRun'].push(runWithFS); // FS is not initialized yet, wait for it
    }

    }
    loadPackage({"files": [{"filename": "/game/resources/NFS_3/gamedata/carmodel/cgt1/car.viv", "start": 0, "end": 118810}, {"filename": "/game/resources/NFS_3/gamedata/carmodel/hat1/car.viv", "start": 118810, "end": 235956}, {"filename": "/game/resources/NFS_3/gamedata/carmodel/traffic/pursuit/ptl1/car.viv", "start": 235956, "end": 354766}, {"filename": "/game/resources/NFS_3/gamedata/carmodel/traffic/tfc1/car.viv", "start": 354766, "end": 471912}, {"filename": "/game/resources/NFS_3/gamedata/carmodel/wdg1/car.viv", "start": 471912, "end": 593266}, {"filename": "/game/resources/NFS_3/gamedata/render/pc/sfx.fsh", "start": 593266, "end": 855810}, {"filename": "/game/resources/misc/missing-a.bmp", "start": 855810, "end": 856896}, {"filename": "/game/resources/misc/missing.bmp", "start": 856896, "end": 857982}, {"filename": "/game/resources/misc/racers.json", "start": 857982, "end": 858420}, {"filename": "/game/resources/misc/sky_textures/CHRD.BMP", "start": 858420, "end": 907626}, {"filename": "/game/resources/misc/skydome/clouds1.tga", "start": 907626, "end": 2480534}, {"filename": "/game/resources/misc/skydome/clouds2.tga", "start": 2480534, "end": 4053442}, {"filename": "/game/resources/misc/skydome/moon.tga", "start": 4053442, "end": 4839918}, {"filename": "/game/resources/misc/skydome/sphere.obj", "start": 4839918, "end": 4904252}, {"filename": "/game/resources/misc/skydome/sun.tga", "start": 4904252, "end": 5952872}, {"filename": "/game/resources/misc/skydome/tint.tga", "start": 5952872, "end": 7001492}, {"filename": "/game/resources/misc/skydome/tint2.tga", "start": 7001492, "end": 8050112}, {"filename": "/game/resources/ui/fonts/LICENSE_DEJAVU.txt", "start": 8050112, "end": 8054928}, {"filename": "/game/resources/ui/fonts/fonts.json", "start": 8054928, "end": 8055049}, {"filename": "/game/resources/ui/fonts/ui-font.ttf", "start": 8055049, "end": 8759177}, {"filename": "/game/resources/ui/menu/images/bgGrillePattern.png", "start": 8759177, "end": 8759992}, {"filename": "/game/resources/ui/menu/images/dropdownButton.png", "start": 8759992, "end": 8761060}, {"filename": "/game/resources/ui/menu/images/dropdownEntry.png", "start": 8761060, "end": 8762128}, {"filename": "/game/resources/ui/menu/images/leftMenuCurve.png", "start": 8762128, "end": 8768355}, {"filename": "/game/resources/ui/menu/images/logo.png", "start": 8768355, "end": 8776103}, {"filename": "/game/resources/ui/menu/images/missingResource.png", "start": 8776103, "end": 8776211}, {"filename": "/game/resources/ui/menu/images/pillButton.png", "start": 8776211, "end": 8777277}, {"filename": "/game/resources/ui/menu/layout/raceOverlay.json", "start": 8777277, "end": 8777298}, {"filename": "/game/resources/ui/menu/resources.json", "start": 8777298, "end": 8778053}, {"filename": "/game/shaders/BillboardShader.frag", "start": 8778053, "end": 8778523}, {"filename": "/game/shaders/BillboardShader.vert", "start": 8778523, "end": 8780267}, {"filename": "/game/shaders/BulletShader.frag", "start": 8780267, "end": 8780355}, {"filename": "/game/shaders/BulletShader.vert", "start": 8780355, "end": 8780856}, {"filename": "/game/shaders/CarShader.frag", "start": 8780856, "end": 8785829}, {"filename": "/game/shaders/CarShader.vert", "start": 8785829, "end": 8787909}, {"filename": "/game/shaders/DepthShader.frag", "start": 8787909, "end": 8788332}, {"filename": "/game/shaders/DepthShader.vert", "start": 8788332, "end": 8788971}, {"filename": "/game/shaders/MiniMapShader.frag", "start": 8788971, "end": 8789068}, {"filename": "/game/shaders/MiniMapShader.vert", "start": 8789068, "end": 8789357}, {"filename": "/game/shaders/ShaderPreamble.h", "start": 8789357, "end": 8789733}, {"filename": "/game/shaders/SkidMarkShader.frag", "start": 8789733, "end": 8791489}, {"filename": "/game/shaders/SkidMarkShader.vert", "start": 8791489, "end": 8792281}, {"filename": "/game/shaders/SkydomeShader.frag", "start": 8792281, "end": 8797146}, {"filename": "/game/shaders/SkydomeShader.vert", "start": 8797146, "end": 8798230}, {"filename": "/game/shaders/TextBillboardShader.frag", "start": 8798230, "end": 8798457}, {"filename": "/game/shaders/TextBillboardShader.vert", "start": 8798457, "end": 8799311}, {"filename": "/game/shaders/TrackShader.frag", "start": 8799311, "end": 8805220}, {"filename": "/game/shaders/TrackShader.vert", "start": 8805220, "end": 8806731}, {"filename": "/game/shaders/UIShader.frag", "start": 8806731, "end": 8806947}, {"filename": "/game/shaders/UIShader.vert", "start": 8806947, "end": 8807272}, {"filename": "/game/shaders/UIShapeShader.frag", "start": 8807272, "end": 8807346}, {"filename": "/game/shaders/UIShapeShader.vert", "start": 8807346, "end": 8807609}, {"filename": "/game/shaders/UITextShader.frag", "start": 8807609, "end": 8807836}, {"filename": "/game/shaders/UITextShader.vert", "start": 8807836, "end": 8808161}], "remote_package_size": 8808161});

  })();
