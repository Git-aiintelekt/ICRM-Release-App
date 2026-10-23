import { useEffect, useRef } from 'react';

const isVideo = (image) => Boolean(image.contentType?.startsWith('video/'));

// A short screen recording (MP4 / WebM), shown like a GIF: muted and looping, playing only while it is on screen,
// so a long page doesn't download every video at once. The controls let viewers pause, seek or go full screen.
function LoopingVideo({ image, className }) {
  const ref = useRef(null);

  useEffect(() => {
    const video = ref.current;
    if (!video || typeof IntersectionObserver === 'undefined') {
      return undefined;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        video.play().catch(() => null); // refused autoplay: the controls still work
      } else {
        video.pause();
      }
    });
    observer.observe(video);
    return () => observer.disconnect();
  }, []);

  return (
    <video
      ref={ref}
      className={className}
      src={image.url}
      aria-label={image.caption ?? 'Video'}
      muted
      loop
      playsInline
      controls
      preload="metadata"
    />
  );
}

// A screenshot (linked to its full size) or a video.
function ScreenshotMedia({ image, className, lazy = false }) {
  if (isVideo(image)) {
    return <LoopingVideo image={image} className={className} />;
  }
  return (
    <a href={image.url} target="_blank" rel="noreferrer" title="Open full size">
      <img src={image.url} alt={image.caption ?? 'Screenshot'} loading={lazy ? 'lazy' : undefined} />
    </a>
  );
}

export default ScreenshotMedia;
