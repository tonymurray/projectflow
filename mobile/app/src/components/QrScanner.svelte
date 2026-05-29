<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import jsQR from 'jsqr';

  const dispatch = createEventDispatcher();

  let video;
  let canvas;
  let stream = null;
  let animFrame = null;
  let status = 'Starting camera…';

  onMount(async () => {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      video.srcObject = stream;
      await video.play();
      await new Promise(resolve => {
        if (video.readyState >= 3) { resolve(); return; }
        video.addEventListener('canplay', resolve, { once: true });
      });
      canvas.width  = video.videoWidth  || 640;
      canvas.height = video.videoHeight || 480;
      status = 'Point at QR code…';
      tick();
    } catch (e) {
      status = 'Camera error: ' + e.message;
    }
  });

  onDestroy(stop);

  function stop() {
    if (animFrame) { cancelAnimationFrame(animFrame); animFrame = null; }
    if (stream)    { stream.getTracks().forEach(t => t.stop()); stream = null; }
  }

  function tick() {
    if (!stream || !video || video.readyState < 2) {
      animFrame = requestAnimationFrame(tick);
      return;
    }
    if (canvas.width !== video.videoWidth && video.videoWidth > 0) {
      canvas.width  = video.videoWidth;
      canvas.height = video.videoHeight;
    }
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height);

    const code = jsQR(img.data, img.width, img.height, { inversionAttempts: 'attemptBoth' });
    if (code) {
      const raw = code.data;
      if (raw.startsWith('nc:/')) {
        const serverM = raw.match(/server:([^&]+)/);
        const userM   = raw.match(/user:([^&]+)/);
        const passM   = raw.match(/password:([^&\s]+)/);
        if (userM && passM) {
          stop();
          dispatch('scanned', {
            server:   serverM ? serverM[1] : '',
            username: userM[1],
            password: passM[1],
          });
          return;
        }
      }
    }
    animFrame = requestAnimationFrame(tick);
  }

  function cancel() {
    stop();
    dispatch('cancel');
  }
</script>

<div class="overlay">
  <div class="inner">
    <p class="status">{status}</p>
    <!-- svelte-ignore a11y-media-has-caption -->
    <video bind:this={video} autoplay playsinline muted class="preview"></video>
    <canvas bind:this={canvas} class="hidden"></canvas>
    <button class="cancel-btn" on:click={cancel}>Cancel</button>
  </div>
</div>

<style>
  .overlay {
    position: fixed; inset: 0; z-index: 100;
    background: #000;
    display: flex; align-items: center; justify-content: center;
  }
  .inner {
    display: flex; flex-direction: column; align-items: center;
    width: 100%; height: 100%;
  }
  .status {
    color: #aaa; font-size: 0.85rem; padding: 16px 0 4px;
    flex-shrink: 0;
  }
  .preview {
    flex: 1; width: 100%; object-fit: cover;
  }
  .hidden { display: none; }
  .cancel-btn {
    flex-shrink: 0; width: 100%; padding: 18px;
    background: #1a1d26; color: #c8ddf7;
    border: none; border-top: 1px solid #2e3244;
    font-size: 1rem;
  }
</style>
