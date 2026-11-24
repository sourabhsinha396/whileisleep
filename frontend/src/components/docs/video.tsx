"use client";

import { Play } from "lucide-react";
import { useState } from "react";

/** A YouTube video. Its player is only loaded once someone presses play. */
export function DocVideo({ id, title }: { id: string; title: string }) {
  const [playing, setPlaying] = useState(false);
  return (
    <div className="relative mt-6 aspect-video overflow-hidden rounded-xl border bg-black">
      {playing ? (
        <iframe
          src={`https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0`}
          title={title}
          className="absolute inset-0 size-full"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          // YouTube refuses to play without knowing which site it is on.
          referrerPolicy="strict-origin-when-cross-origin"
          allowFullScreen
        />
      ) : (
        <button onClick={() => setPlaying(true)} aria-label={`Play the video: ${title}`} className="group absolute inset-0 size-full">
          {/* YouTube's own picture; next/image would only add a hop. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`https://i.ytimg.com/vi/${id}/hqdefault.jpg`} alt="" className="size-full object-cover opacity-90 transition-opacity group-hover:opacity-100" />
          <span className="absolute inset-0 grid place-items-center">
            <span className="grid size-16 place-items-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform group-hover:scale-105">
              <Play size={26} className="ml-1 fill-current" />
            </span>
          </span>
        </button>
      )}
    </div>
  );
}
