import React, { useState } from 'react';
import {
  Download,
  Copy,
  Check,
  Play,
  Square,
  Cpu,
  Scissors,
  Film,
  Music,
  Settings,
  FileCode,
  RefreshCw,
  FolderOpen
} from 'lucide-react';

import corePyRaw from '../core.py?raw';
import appPyRaw from '../app.py?raw';
import webAppPyRaw from '../web_app.py?raw';
import webIndexHtmlRaw from '../web/index.html?raw';
import startDesktopBatRaw from '../start_desktop.bat?raw';
import startWebBatRaw from '../start_web.bat?raw';
import installerIssRaw from '../installer.iss?raw';
import buildExeYmlRaw from '../.github/workflows/build_exe.yml?raw';

type SceneType = 'lip-sync' | 'b-roll' | 'action' | 'outro';

interface SceneItem {
  id: number;
  type: SceneType;
  start: number;
  end: number;
  duration: number;
  prompt: string;
  custom_image: string;
  status: 'ожидание' | 'рендер' | 'готово' | 'ошибка';
}

const SCENE_TYPE_LABELS: Record<SceneType, string> = {
  'lip-sync': 'Синхронизация губ (вокал)',
  'b-roll': 'Перебивка / атмосфера (B-Roll)',
  'action': 'Динамичная сцена (Action)',
  'outro': 'Финал (Outro)'
};

const PRESETS: Record<string, Array<{ type: SceneType; prompt: string }>> = {
  cyber_cat: [
    {
      type: 'lip-sync',
      prompt:
        'Medium close-up of a charismatic anthropomorphic ginger tabby cat wearing a vintage leather jacket and neon headphones, singing emotionally into a studio condenser microphone, expressive mouth movement, cinematic studio lighting, shallow depth of field, 4k'
    },
    {
      type: 'b-roll',
      prompt:
        'Wide cinematic shot of a rain-slicked cyberpunk Tokyo alley at night, glowing neon reflections on wet asphalt, steam rising from vents, atmospheric fog, moody blue and magenta lighting, no characters, 4k'
    },
    {
      type: 'lip-sync',
      prompt:
        'Close-up portrait of the ginger tabby cat singing passionately on a rooftop stage, neon city skyline bokeh in background, expressive facial animation and lip sync, dramatic rim light'
    },
    {
      type: 'action',
      prompt:
        'Dynamic tracking shot of a sleek futuristic motorcycle speeding through a neon-lit highway tunnel, motion blur, sparks and light trails, high-octane cinematic action'
    },
    {
      type: 'b-roll',
      prompt:
        'Macro shot of vintage analog synthesizer keys and glowing vacuum tubes pulsing to music rhythm, warm amber studio lighting, shallow focus'
    },
    {
      type: 'outro',
      prompt:
        'Slow pull-back wide shot of the neon city skyline at dawn, soft golden sunlight breaking through dark clouds over calm ocean water, cinematic fade out'
    }
  ],
  sea_voyage: [
    {
      type: 'lip-sync',
      prompt:
        'Close-up of a rugged sea captain cat in a knitted fisherman sweater singing heartily on the wooden deck of a ship, wind ruffling fur, warm sunset lighting, natural lip synchronization'
    },
    {
      type: 'b-roll',
      prompt:
        'Breathtaking aerial view of turquoise ocean waves crashing against dramatic basalt sea cliffs, golden hour sunlight, sea spray and foam, cinematic nature documentary style'
    },
    {
      type: 'action',
      prompt:
        'Dynamic shot of a school of silver tuna leaping through crystal-clear ocean waves in slow motion, sunbeams piercing underwater, vibrant marine life'
    },
    {
      type: 'lip-sync',
      prompt:
        'Medium shot of the captain cat at the ship helm singing with emotion, lantern light glowing in evening mist, expressive mouth movements, film grain'
    },
    {
      type: 'outro',
      prompt:
        'Wide tranquil shot of a wooden sailboat silhouette gliding toward a glowing horizon under a starry night sky, calm sea reflections'
    }
  ]
};

const SOURCE_FILES = [
  { name: 'core.py', path: 'core.py', lang: 'python', content: corePyRaw },
  { name: 'app.py', path: 'app.py', lang: 'python', content: appPyRaw },
  { name: 'web_app.py', path: 'web_app.py', lang: 'python', content: webAppPyRaw },
  { name: 'web/index.html', path: 'web/index.html', lang: 'html', content: webIndexHtmlRaw },
  { name: 'installer.iss', path: 'installer.iss', lang: 'ini', content: installerIssRaw },
  {
    name: 'build_exe.yml',
    path: '.github/workflows/build_exe.yml',
    lang: 'yaml',
    content: buildExeYmlRaw
  },
  { name: 'start_desktop.bat', path: 'start_desktop.bat', lang: 'bat', content: startDesktopBatRaw },
  { name: 'start_web.bat', path: 'start_web.bat', lang: 'bat', content: startWebBatRaw }
];

function calcWanFrames(durationSec: number, fps = 24): number {
  const rawFrames = Math.max(17, Math.ceil(durationSec * fps));
  const k = Math.ceil((rawFrames - 1) / 4.0);
  return 4 * k + 1;
}

export default function App() {
  const [activeView, setActiveView] = useState<'studio' | 'sources'>('studio');
  const [selectedFileIndex, setSelectedFileIndex] = useState<number>(0);
  const [copiedFile, setCopiedFile] = useState<string | null>(null);

  // Project & Config State
  const [projectName, setProjectName] = useState('cyber_cat_clip');
  const [aceDir, setAceDir] = useState('C:\\AI\\ACE-Step-1.5');
  const [comfyRoot, setComfyRoot] = useState('C:\\AI\\ComfyUI_windows_portable');
  const [wfLipsync, setWfLipsync] = useState('C:\\AI\\wan2.2_s2v_api.json');
  const [wfBroll, setWfBroll] = useState('C:\\AI\\wan2.2_i2v_api.json');
  const [lowVram, setLowVram] = useState(false);
  const [reserveVram, setReserveVram] = useState(2.0);
  const [comfy8188Online, setComfy8188Online] = useState(true);
  const [comfy8189Online, setComfy8189Online] = useState(false);
  const [aceOnline, setAceOnline] = useState(true);

  // Song & Audio State
  const [musicPrompt, setMusicPrompt] = useState(
    'upbeat synthwave pop, melodic female vocal, 120 bpm, emotional chorus'
  );
  const [lyrics, setLyrics] = useState(
    '[Verse 1]\nNeon lights across the bay\nChasing shadows far away\n\n[Chorus]\nWe are running through the night\nGlowing in electric light'
  );
  const [songDuration, setSongDuration] = useState<number>(28.45);
  const [songSeed, setSongSeed] = useState<number>(42);
  const [songPath, setSongPath] = useState<string>(
    'C:\\AI\\MusicVideoStudio\\projects\\cyber_cat_clip\\audio\\song.mp3'
  );
  const [heroImage, setHeroImage] = useState<string>(
    'C:\\AI\\MusicVideoStudio\\assets\\ginger_cat_vocalist.png'
  );

  // Storyboard State
  const [presetName, setPresetName] = useState<'cyber_cat' | 'sea_voyage'>('cyber_cat');
  const [sceneDuration, setSceneDuration] = useState<number>(5.0);
  const [skipCompleted, setSkipCompleted] = useState<boolean>(true);
  const [storyboard, setStoryboard] = useState<SceneItem[]>(() => {
    const templates = PRESETS.cyber_cat;
    const list: SceneItem[] = [];
    let cursor = 0;
    let idx = 1;
    const total = 28.45;
    while (cursor < total - 0.05) {
      const rem = Number((total - cursor).toFixed(2));
      const dur = Number(Math.min(5.0, rem).toFixed(2));
      const tpl = templates[(idx - 1) % templates.length];
      list.push({
        id: idx,
        type: cursor + dur >= total - 0.05 ? 'outro' : tpl.type,
        start: Number(cursor.toFixed(2)),
        end: Number((cursor + dur).toFixed(2)),
        duration: dur,
        prompt: tpl.prompt,
        custom_image: '',
        status: idx <= 2 ? 'готово' : 'ожидание'
      });
      cursor = Number((cursor + dur).toFixed(2));
      idx++;
    }
    return list;
  });

  const [logs, setLogs] = useState<string[]>([
    '[INFO] Открыт проект "cyber_cat_clip": длительность трека (FFprobe) 28.450 сек, сцен: 6',
    '[GPU] Сервер http://127.0.0.1:8188 ОНЛАЙН — NVIDIA GeForce RTX 4090 (Свободно VRAM: 21.40 / 24.00 ГБ)'
  ]);

  const appendLog = (msg: string) => {
    setLogs((prev) => [...prev, msg]);
  };

  const handleStopAce = () => {
    setAceOnline(false);
    appendLog(
      '[INFO] Выполнено: taskkill /F /T /PID 14820 — дерево процессов ACE-Step 1.5 остановлено. Освобождено ~4.2 ГБ VRAM.'
    );
  };

  const handleStartAce = () => {
    setAceOnline(true);
    appendLog('[INFO] Запущен сервер ACE-Step 1.5 на http://127.0.0.1:8001 (PID=18492)');
  };

  const handleProbeAudio = () => {
    appendLog(
      `[AUDIO] FFprobe анализ "${songPath}" -> точная длительность: ${songDuration.toFixed(3)} сек.`
    );
  };

  const handleGenerateLyrics = () => {
    appendLog('[ACE] POST /format_input (модель acestep-5Hz-lm-0.6B) -> текст и структурные теги отформатированы.');
    setLyrics(
      '[Verse 1]\nNeon lights across the bay\nChasing shadows far away\nSynthesizers in the rain\nWashing out the static pain\n\n[Chorus]\nWe are running through the night\nGlowing in electric light'
    );
  };

  const handleGenerateSong = () => {
    appendLog(
      `[ACE] POST /release_task (модель acestep-v15-turbo, длительность ${songDuration}s, seed=${songSeed}) -> поллинг /query_result...`
    );
    appendLog(
      `[AUDIO] Сгенерирован файл projects/${projectName}/audio/song.mp3 — FFprobe длительность: ${songDuration.toFixed(3)} сек.`
    );
  };

  const handleRebuildStoryboard = (preset = presetName, baseDur = sceneDuration) => {
    const templates = PRESETS[preset] || PRESETS.cyber_cat;
    const list: SceneItem[] = [];
    let cursor = 0;
    let idx = 1;
    const total = songDuration;
    while (cursor < total - 0.05) {
      const rem = Number((total - cursor).toFixed(2));
      const dur = Number(Math.min(baseDur, rem).toFixed(2));
      if (dur < 1.2 && list.length > 0) {
        list[list.length - 1].duration = Number((list[list.length - 1].duration + dur).toFixed(2));
        list[list.length - 1].end = Number((cursor + dur).toFixed(2));
        break;
      }
      const tpl = templates[(idx - 1) % templates.length];
      list.push({
        id: idx,
        type: cursor + dur >= total - 0.05 && idx > 2 ? 'outro' : tpl.type,
        start: Number(cursor.toFixed(2)),
        end: Number((cursor + dur).toFixed(2)),
        duration: dur,
        prompt: tpl.prompt,
        custom_image: '',
        status: 'ожидание'
      });
      cursor = Number((cursor + dur).toFixed(2));
      idx++;
    }
    setStoryboard(list);
    appendLog(
      `[STORYBOARD] Сформирована раскадровка "${preset}" (${list.length} сцен на ${total.toFixed(2)} сек). Сохранено в data/storyboard.json`
    );
  };

  const handleSliceAudio = () => {
    storyboard.forEach((sc) => {
      appendLog(
        `[FFMPEG] ffmpeg -y -ss ${sc.start.toFixed(2)} -t ${sc.duration.toFixed(2)} -i song.mp3 -ac 1 -ar 16000 -c:a pcm_s16le segments/scene_${String(sc.id).padStart(3, '0')}.wav`
      );
    });
  };

  const handleUpdateScene = (id: number, field: 'prompt' | 'type', value: string) => {
    setStoryboard((prev) =>
      prev.map((sc) =>
        sc.id === id
          ? {
              ...sc,
              [field]: value
            }
          : sc
      )
    );
    appendLog(`[STORYBOARD] Сцена #${String(id).padStart(3, '0')} автоматически сохранена в data/storyboard.json`);
  };

  const handleRenderSingle = (id: number) => {
    const sc = storyboard.find((s) => s.id === id);
    if (!sc) return;
    const frames = calcWanFrames(sc.duration, 24);
    const wfUsed = sc.type === 'lip-sync' ? wfLipsync : wfBroll || wfLipsync;
    appendLog(
      `[COMFY] Пересоздание сцены #${String(id).padStart(3, '0')} (${sc.type}, ${frames} кадров [4k+1], шаблон: ${wfUsed})...`
    );
    setStoryboard((prev) => prev.map((s) => (s.id === id ? { ...s, status: 'готово' } : s)));
  };

  const handleQueueAll = () => {
    const onlineUrls: string[] = [];
    if (comfy8188Online) onlineUrls.push('http://127.0.0.1:8188');
    if (comfy8189Online) onlineUrls.push('http://127.0.0.1:8189');

    if (onlineUrls.length === 0) {
      appendLog('[ERROR] Ни один сервер ComfyUI (8188, 8189) не запущен!');
      return;
    }

    const pending = storyboard.filter((s) => !(skipCompleted && s.status === 'готово'));
    appendLog(
      `[QUEUE] Доступно серверов ComfyUI: ${onlineUrls.length} (${onlineUrls.join(', ')}). Направление задач с шагом ${onlineUrls.length}. Сцен в очереди: ${pending.length}`
    );

    setStoryboard((prev) =>
      prev.map((s) => {
        if (skipCompleted && s.status === 'готово') return s;
        return { ...s, status: 'готово' };
      })
    );
  };

  const handleAssemble = () => {
    storyboard.forEach((sc) => {
      appendLog(
        `[SYNC] Выравнивание сцены #${String(sc.id).padStart(3, '0')}: обрезка ${calcWanFrames(sc.duration, 24)} кадров -> строго -t ${sc.duration.toFixed(4)} -r 24 (устранение Lip-Sync Drift)`
      );
    });
    appendLog(
      `[FFMPEG] Финальная сборка: ffmpeg -f concat -safe 0 -i concat_list.txt -i song.mp3 -c:v libx264 -preset fast -crf 18 -r 24 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest projects/${projectName}/output/final_music_video.mp4`
    );
  };

  const copyFileContent = (name: string, content: string) => {
    navigator.clipboard.writeText(content);
    setCopiedFile(name);
    setTimeout(() => setCopiedFile(null), 2000);
  };

  const downloadFileContent = (name: string, content: string) => {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name.replace('/', '_');
    a.click();
    URL.revokeObjectURL(url);
  };

  const selectedFile = SOURCE_FILES[selectedFileIndex];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Bar Contract: Zone 1 Brand — Zone 2 Nav Links — Zone 3 Primary Action */}
      <header className="flex items-center justify-between gap-8 px-6 py-3.5 border-b border-slate-800 bg-slate-900/90">
        <a
          href="#top"
          onClick={(e) => {
            e.preventDefault();
            setActiveView('studio');
          }}
          className="text-base font-bold tracking-tight text-slate-100 whitespace-nowrap shrink-0"
        >
          MusicVideoStudio
        </a>

        <nav className="flex items-center gap-6 text-sm font-medium text-slate-400">
          <button
            onClick={() => setActiveView('studio')}
            className={`hover:text-slate-100 transition-colors whitespace-nowrap shrink-0 pb-0.5 ${
              activeView === 'studio' ? 'text-slate-100 border-b-2 border-blue-500' : ''
            }`}
          >
            Студия и конвейер
          </button>
          <button
            onClick={() => setActiveView('sources')}
            className={`hover:text-slate-100 transition-colors whitespace-nowrap shrink-0 pb-0.5 ${
              activeView === 'sources' ? 'text-slate-100 border-b-2 border-blue-500' : ''
            }`}
          >
            Исходный код и CI/CD (8 файлов)
          </button>
        </nav>

        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={() => {
              setActiveView('sources');
              downloadFileContent(selectedFile.name, selectedFile.content);
            }}
            className="px-4 py-2 text-xs font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-500 transition-colors whitespace-nowrap shrink-0 flex items-center gap-1.5"
          >
            <Download className="w-3.5 h-3.5" />
            Скачать {selectedFile.name}
          </button>
        </div>
      </header>

      {activeView === 'studio' ? (
        <main className="flex-1 max-w-[1440px] w-full mx-auto px-6 py-5 grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Project, ACE-Step 1.5, VRAM Settings */}
          <div className="lg:col-span-4 space-y-5">
            {/* Project & Server Control */}
            <section className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-3">
                <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                  <FolderOpen className="w-4 h-4 text-blue-400" />
                  Проект и управление VRAM
                </h2>
                <span className="text-xs text-slate-400 font-mono tabular-nums">
                  projects/{projectName}
                </span>
              </div>

              <div className="flex gap-2 mb-3">
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  className="flex-1 bg-slate-950 border border-slate-800 rounded-md px-3 py-1.5 text-xs text-slate-100"
                  placeholder="Имя папки проекта"
                />
                <button
                  onClick={() =>
                    appendLog(
                      `[INFO] Проект "${projectName}" синхронизирован: проверены audio/song.mp3, data/storyboard.json и clips/scene_XXX.mp4`
                    )
                  }
                  className="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-md whitespace-nowrap shrink-0"
                >
                  Открыть проект
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={handleStartAce}
                  className="px-3 py-2 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-md flex items-center justify-center gap-1.5 whitespace-nowrap"
                >
                  <Play className="w-3.5 h-3.5 text-emerald-400" />
                  Запустить ACE API
                </button>
                <button
                  onClick={handleStopAce}
                  className="px-3 py-2 text-xs font-medium bg-rose-950/70 hover:bg-rose-900/80 text-rose-200 border border-rose-800/60 rounded-md flex items-center justify-center gap-1.5 whitespace-nowrap"
                >
                  <Square className="w-3.5 h-3.5 text-rose-400" />
                  Остановить ACE API
                </button>
              </div>

              <div className="mt-3 pt-3 border-t border-slate-800/80 text-xs text-slate-400 space-y-2">
                <div className="flex items-center justify-between">
                  <span>ACE-Step 1.5 (127.0.0.1:8001):</span>
                  <span className={aceOnline ? 'text-emerald-400 font-medium' : 'text-slate-500'}>
                    {aceOnline ? 'Онлайн (модель в VRAM)' : 'Остановлен (VRAM свободна)'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                    <input
                      type="checkbox"
                      checked={comfy8188Online}
                      onChange={(e) => setComfy8188Online(e.target.checked)}
                    />
                    ComfyUI #1 (8188 · GPU 0)
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                    <input
                      type="checkbox"
                      checked={comfy8189Online}
                      onChange={(e) => setComfy8189Online(e.target.checked)}
                    />
                    ComfyUI #2 (8189 · GPU 1)
                  </label>
                </div>
              </div>
            </section>

            {/* Step 1: ACE-Step 1.5 Song & FFprobe */}
            <section className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <h2 className="text-sm font-semibold text-slate-100 border-b border-slate-800 pb-2.5 mb-3 flex items-center gap-2">
                <Music className="w-4 h-4 text-blue-400" />
                1. Генерация песни (ACE-Step 1.5) и FFprobe
              </h2>

              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    Теги стиля (Prompt для acestep-v15-turbo)
                  </label>
                  <input
                    type="text"
                    value={musicPrompt}
                    onChange={(e) => setMusicPrompt(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-1.5 text-xs text-slate-100"
                  />
                </div>

                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    Текст песни (Lyrics — /format_input с acestep-5Hz-lm-0.6B)
                  </label>
                  <textarea
                    rows={4}
                    value={lyrics}
                    onChange={(e) => setLyrics(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-1.5 text-xs font-mono text-slate-100"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">
                      Точная длительность (сек)
                    </label>
                    <input
                      type="number"
                      step="0.05"
                      value={songDuration}
                      onChange={(e) => setSongDuration(Number(e.target.value) || 30)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-1.5 text-xs font-mono tabular-nums text-slate-100"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Seed</label>
                    <input
                      type="number"
                      value={songSeed}
                      onChange={(e) => setSongSeed(Number(e.target.value) || 42)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-1.5 text-xs font-mono tabular-nums text-slate-100"
                    />
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={handleGenerateLyrics}
                    className="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-md whitespace-nowrap"
                  >
                    Сгенерировать текст
                  </button>
                  <button
                    onClick={handleGenerateSong}
                    className="px-3 py-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white rounded-md whitespace-nowrap"
                  >
                    Сгенерировать трек
                  </button>
                  <button
                    onClick={handleProbeAudio}
                    className="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-md whitespace-nowrap"
                  >
                    FFprobe тест
                  </button>
                </div>

                <div className="pt-2 border-t border-slate-800/80 space-y-2">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">
                      Аудиофайл проекта (audio/song.mp3)
                    </label>
                    <input
                      type="text"
                      value={songPath}
                      onChange={(e) => setSongPath(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-md px-2.5 py-1 text-xs font-mono text-slate-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">
                      Изображение главного героя (передаётся только в сцены lip-sync)
                    </label>
                    <input
                      type="text"
                      value={heroImage}
                      onChange={(e) => setHeroImage(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-md px-2.5 py-1 text-xs font-mono text-slate-300"
                    />
                  </div>
                </div>
              </div>
            </section>

            {/* Step 3: Paths & VRAM Config */}
            <section className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <h2 className="text-sm font-semibold text-slate-100 border-b border-slate-800 pb-2.5 mb-3 flex items-center gap-2">
                <Settings className="w-4 h-4 text-blue-400" />
                3. Настройки путей и VRAM (config.json)
              </h2>

              <div className="space-y-2.5 text-xs">
                <div>
                  <label className="block text-slate-400 mb-1">ace_dir</label>
                  <input
                    type="text"
                    value={aceDir}
                    onChange={(e) => setAceDir(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-2.5 py-1 font-mono text-slate-200"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">comfy_root</label>
                  <input
                    type="text"
                    value={comfyRoot}
                    onChange={(e) => setComfyRoot(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-2.5 py-1 font-mono text-slate-200"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">
                    workflow_lipsync (Wan2.2 Sound-to-Video)
                  </label>
                  <input
                    type="text"
                    value={wfLipsync}
                    onChange={(e) => setWfLipsync(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-2.5 py-1 font-mono text-slate-200"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">
                    workflow_broll (Wan2.2 I2V/T2V без синхронизации губ)
                  </label>
                  <input
                    type="text"
                    value={wfBroll}
                    onChange={(e) => setWfBroll(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-2.5 py-1 font-mono text-slate-200"
                  />
                </div>

                <div className="pt-2 flex items-center justify-between gap-4">
                  <label className="flex items-center gap-2 cursor-pointer text-slate-200">
                    <input
                      type="checkbox"
                      checked={lowVram}
                      onChange={(e) => setLowVram(e.target.checked)}
                    />
                    Флаг <code className="text-blue-400">--lowvram</code> (для 12 ГБ VRAM)
                  </label>
                  <div className="flex items-center gap-1.5">
                    <span className="text-slate-400">--reserve-vram:</span>
                    <input
                      type="number"
                      step="0.5"
                      value={reserveVram}
                      onChange={(e) => setReserveVram(Number(e.target.value))}
                      className="w-16 bg-slate-950 border border-slate-800 rounded px-2 py-0.5 font-mono tabular-nums text-right"
                    />
                    <span className="text-slate-500">ГБ</span>
                  </div>
                </div>
              </div>
            </section>
          </div>

          {/* Right Column: Storyboard Table, Queue & Logs */}
          <div className="lg:col-span-8 flex flex-col gap-5">
            <section className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex-1 flex flex-col">
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-3 mb-3">
                <div>
                  <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                    <Film className="w-4 h-4 text-blue-400" />
                    2. Раскадровка сцен (Wan2.2: разделение lip-sync / b-roll и контроль 4k+1 кадров)
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Промпты для энкодера UMT5 — строго на английском языке · При сборке каждый клип обрезается до{' '}
                    <code className="text-slate-300">-t duration -r 24</code> для устранения рассинхрона
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <select
                    value={presetName}
                    onChange={(e) => {
                      const val = e.target.value as 'cyber_cat' | 'sea_voyage';
                      setPresetName(val);
                      handleRebuildStoryboard(val, sceneDuration);
                    }}
                    className="bg-slate-950 border border-slate-800 rounded-md px-2.5 py-1.5 text-xs text-slate-200"
                  >
                    <option value="cyber_cat">Пресет: Cyber Cat</option>
                    <option value="sea_voyage">Пресет: Sea Voyage</option>
                  </select>

                  <input
                    type="number"
                    step="0.5"
                    value={sceneDuration}
                    onChange={(e) => setSceneDuration(Number(e.target.value) || 5.0)}
                    className="w-16 bg-slate-950 border border-slate-800 rounded-md px-2 py-1.5 text-xs font-mono tabular-nums text-slate-200"
                    title="Длительность сцены (сек)"
                  />

                  <button
                    onClick={() => handleRebuildStoryboard(presetName, sceneDuration)}
                    className="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-md whitespace-nowrap"
                  >
                    Создать раскадровку
                  </button>
                </div>
              </div>

              {/* Action Toolbar */}
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3 bg-slate-950/70 border border-slate-800/80 rounded-md p-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={handleSliceAudio}
                    className="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-md flex items-center gap-1.5 whitespace-nowrap"
                  >
                    <Scissors className="w-3.5 h-3.5 text-amber-400" />
                    Нарезать WAV (16kHz mono)
                  </button>

                  <button
                    onClick={handleQueueAll}
                    className="px-3 py-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white rounded-md flex items-center gap-1.5 whitespace-nowrap"
                  >
                    <Cpu className="w-3.5 h-3.5" />
                    В очередь ComfyUI ({comfy8188Online && comfy8189Online ? '2 GPU: шаг 2' : '1 GPU: шаг 1'})
                  </button>

                  <label className="flex items-center gap-1.5 text-xs text-slate-300 ml-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={skipCompleted}
                      onChange={(e) => setSkipCompleted(e.target.checked)}
                    />
                    Пропускать готовые сцены
                  </label>
                </div>

                <button
                  onClick={handleAssemble}
                  className="px-3.5 py-1.5 text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white rounded-md flex items-center gap-1.5 whitespace-nowrap"
                >
                  <Film className="w-3.5 h-3.5" />
                  Финальная сборка MP4 (CRF 18)
                </button>
              </div>

              {/* High-Density Data Grid */}
              <div className="overflow-x-auto flex-1">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/50">
                      <th className="py-2.5 px-2.5 font-medium w-10">#</th>
                      <th className="py-2.5 px-2.5 font-medium w-44">Тип сцены (RU метка)</th>
                      <th className="py-2.5 px-2.5 font-medium w-28">Таймкод</th>
                      <th className="py-2.5 px-2.5 font-medium w-28">Wan кадры (4k+1)</th>
                      <th className="py-2.5 px-2.5 font-medium">Английский промпт (UMT5)</th>
                      <th className="py-2.5 px-2.5 font-medium w-24">Статус</th>
                      <th className="py-2.5 px-2.5 font-medium w-32 text-right">Действие</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {storyboard.map((sc) => {
                      const wanFrames = calcWanFrames(sc.duration, 24);
                      const rawWanDur = (wanFrames / 24).toFixed(3);
                      return (
                        <tr key={sc.id} className="hover:bg-slate-800/30 transition-colors">
                          <td className="py-2.5 px-2.5 font-mono tabular-nums text-slate-400">
                            {String(sc.id).padStart(2, '0')}
                          </td>
                          <td className="py-2.5 px-2.5">
                            <select
                              value={sc.type}
                              onChange={(e) =>
                                handleUpdateScene(sc.id, 'type', e.target.value as SceneType)
                              }
                              className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-200"
                            >
                              {Object.entries(SCENE_TYPE_LABELS).map(([k, label]) => (
                                <option key={k} value={k}>
                                  {k} · {label}
                                </option>
                              ))}
                            </select>
                            <div className="text-[11px] text-slate-400 mt-1">
                              {sc.type === 'lip-sync'
                                ? 'Герой + WAV вокал -> S2V'
                                : 'Без портрета героя · звук 0.0'}
                            </div>
                          </td>
                          <td className="py-2.5 px-2.5 font-mono tabular-nums text-slate-300">
                            <div>
                              {sc.start.toFixed(2)}s – {sc.end.toFixed(2)}s
                            </div>
                            <div className="text-slate-500">Длит.: {sc.duration.toFixed(2)}s</div>
                          </td>
                          <td className="py-2.5 px-2.5 font-mono tabular-nums">
                            <div className="text-slate-200">{wanFrames} кадр.</div>
                            <div className="text-[11px] text-slate-500">
                              {rawWanDur}s → {sc.duration.toFixed(2)}s
                            </div>
                          </td>
                          <td className="py-2.5 px-2.5">
                            <input
                              type="text"
                              value={sc.prompt}
                              onChange={(e) => handleUpdateScene(sc.id, 'prompt', e.target.value)}
                              className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-100 focus:border-blue-500 focus:outline-none"
                            />
                          </td>
                          <td className="py-2.5 px-2.5 font-medium">
                            {sc.status === 'готово' ? (
                              <span className="text-emerald-400">готово</span>
                            ) : sc.status === 'рендер' ? (
                              <span className="text-amber-400">рендер</span>
                            ) : (
                              <span className="text-slate-400">ожидание</span>
                            )}
                          </td>
                          <td className="py-2.5 px-2.5 text-right">
                            <button
                              onClick={() => handleRenderSingle(sc.id)}
                              className="px-2.5 py-1 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 rounded inline-flex items-center gap-1 whitespace-nowrap"
                            >
                              <RefreshCw className="w-3 h-3" />
                              Пересоздать
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Pipeline Execution Log */}
            <section className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-slate-300">
                  Журнал команд конвейера (ACE-Step 1.5 / ComfyUI / FFmpeg)
                </span>
                <button
                  onClick={() => setLogs([])}
                  className="text-xs text-slate-400 hover:text-slate-200"
                >
                  Очистить журнал
                </button>
              </div>
              <div className="bg-slate-950 border border-slate-800 rounded-md p-3 h-36 overflow-y-auto font-mono text-xs text-slate-300 space-y-1">
                {logs.map((line, i) => (
                  <div key={i} className="leading-relaxed">
                    {line}
                  </div>
                ))}
              </div>
            </section>
          </div>
        </main>
      ) : (
        /* Source Code Explorer & Downloader for all 6 required files */
        <main className="flex-1 max-w-[1440px] w-full mx-auto px-6 py-5 flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-4 bg-slate-900 border border-slate-800 rounded-lg p-4">
            <div className="flex flex-wrap items-center gap-2">
              {SOURCE_FILES.map((file, idx) => (
                <button
                  key={file.name}
                  onClick={() => setSelectedFileIndex(idx)}
                  className={`px-3.5 py-2 rounded-md text-xs font-mono font-medium transition-colors flex items-center gap-2 whitespace-nowrap ${
                    selectedFileIndex === idx
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-950 text-slate-300 hover:bg-slate-800 border border-slate-800'
                  }`}
                >
                  <FileCode className="w-3.5 h-3.5" />
                  {file.name}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => copyFileContent(selectedFile.name, selectedFile.content)}
                className="px-3.5 py-2 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-100 rounded-md flex items-center gap-1.5 whitespace-nowrap"
              >
                {copiedFile === selectedFile.name ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                    Скопировано
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    Скопировать код
                  </>
                )}
              </button>
              <button
                onClick={() => downloadFileContent(selectedFile.name, selectedFile.content)}
                className="px-3.5 py-2 text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white rounded-md flex items-center gap-1.5 whitespace-nowrap"
              >
                <Download className="w-3.5 h-3.5" />
                Скачать {selectedFile.name}
              </button>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden flex-1 flex flex-col">
            <div className="px-4 py-2.5 bg-slate-950 border-b border-slate-800 flex items-center justify-between text-xs font-mono text-slate-400">
              <span>Файл: {selectedFile.path} (Python 3.11+ Standard Library Only)</span>
              <span>Строк: {selectedFile.content.split('\n').length}</span>
            </div>
            <pre className="p-4 text-xs font-mono text-slate-200 overflow-x-auto overflow-y-auto max-h-[680px] leading-relaxed">
              <code>{selectedFile.content}</code>
            </pre>
          </div>
        </main>
      )}
    </div>
  );
}
