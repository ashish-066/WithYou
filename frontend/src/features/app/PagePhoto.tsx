/**
 * Study a page from your book: take a photo, the buddy reads it (Gemini, ~2 s),
 * shows the topic and key ideas, then the session teaches from that page.
 * The photo is shrunk on the phone first (max 1600 px JPEG) so uploads are quick.
 */
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Camera, RotateCcw } from 'lucide-react';

import { readPage, type ReadPage } from '@/services/api';
import { Buddy } from './Buddy';
import { sessionUrl } from './HomePage';
import { usePrefs } from './prefs';
import { strings } from './strings';

async function shrink(file: File, max = 1600): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.82);
}

export function PagePhoto() {
  const { language } = usePrefs();
  const t = strings(language).page;
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState<ReadPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onFile = async (file?: File) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setPage(null);
    try {
      setPage(await readPage(await shrink(file), language));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  };

  return (
    <section aria-labelledby="page-title" className="sketch bg-surface p-5">
      <input
        ref={input}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(e) => onFile(e.target.files?.[0])}
      />
      {busy ? (
        <div className="flex flex-col items-center py-2 text-center">
          <Buddy mood="thinking" size={96} />
          <p role="status" className="mt-2 font-hand text-lead text-terracotta">
            {t.reading}
          </p>
        </div>
      ) : page ? (
        <div>
          <h2 id="page-title" className="text-meta text-muted">
            {t.found}
          </h2>
          <p className="mt-1 font-display text-h3 font-bold text-ink">{page.topic}</p>
          {page.summary && <p className="mt-1 text-body text-muted">{page.summary}</p>}
          <ul className="mt-3 space-y-1.5">
            {page.points.map((p) => (
              <li key={p} className="flex gap-2 text-body text-ink">
                <span aria-hidden className="mt-2 h-2 w-2 shrink-0 rounded-full bg-accent" />
                {p}
              </li>
            ))}
          </ul>
          <button
            onClick={() => navigate(sessionUrl('study', page.topic, page.page_id))}
            className="sketch mt-4 inline-flex h-12 w-full items-center justify-center gap-2 bg-accent text-lead font-semibold text-accent-on"
          >
            {t.start}
            <ArrowRight size={18} aria-hidden />
          </button>
          <button
            onClick={() => input.current?.click()}
            className="mt-2 inline-flex h-10 w-full items-center justify-center gap-2 text-body text-muted"
          >
            <RotateCcw size={16} aria-hidden />
            {t.retake}
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-4">
          <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-turmeric-soft text-ink">
            <Camera size={26} aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="page-title" className="font-display text-lead font-bold text-ink">
              {t.title}
            </h2>
            <p className="text-meta text-muted">{t.body}</p>
          </div>
        </div>
      )}
      {!busy && !page && (
        <button
          onClick={() => input.current?.click()}
          className="sketch mt-4 inline-flex h-12 w-full items-center justify-center gap-2 bg-ink text-lead font-semibold text-canvas"
        >
          <Camera size={18} aria-hidden />
          {t.take}
        </button>
      )}
      {error && (
        <p role="alert" className="mt-3 text-body text-bad">
          {error}
        </p>
      )}
    </section>
  );
}
