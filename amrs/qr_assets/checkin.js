'use strict';

const byId = id => document.getElementById(id);
const login = byId('login');
const face = byId('face');
const video = byId('video');
const verify = byId('verify');
const mark = byId('mark');
const restart = byId('restart');
const notice = byId('status');
const preview = byId('preview');
const faceBox = byId('face-box');
const still = byId('still');
const base = window.location.pathname.replace(/\/$/, '');
const steps = document.querySelectorAll('.steps li');
const prompts = {
  center: 'Look straight at the camera',
  left: 'Turn your head slightly left ←',
  right: 'Turn your head slightly right →',
};
let stream;
let pose = 'center';
let active = true;
let generation = 0;
let verificationTimer;
let overlay;

function message(text, error = false) {
  notice.textContent = text;
  notice.classList.toggle('error', error);
}

function step(index) {
  steps.forEach((item, i) => {
    if (i === index) item.setAttribute('aria-current', 'step');
    else item.removeAttribute('aria-current');
  });
}

async function send(action, body, contentType) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const options = {
      method: 'POST', cache: 'no-store', credentials: 'same-origin', signal: controller.signal,
    };
    if (body !== undefined) {
      options.body = body;
      options.headers = {'Content-Type': contentType};
    }
    const response = await fetch(base + '/' + action, options);
    let data;
    try { data = await response.json(); }
    catch { data = {message: 'The check-in service did not respond. Try again.'}; }
    if (!response.ok && !data.retry) {
      const error = new Error(data.message);
      error.status = response.status;
      throw error;
    }
    return data;
  } finally {
    clearTimeout(timeout);
  }
}

function stopCamera(keepPreview = false) {
  if (stream) stream.getTracks().forEach(track => track.stop());
  stream = undefined;
  video.srcObject = null;
  byId('pose').hidden = true;
  if (keepPreview) return;
  still.hidden = true;
  still.width = 0;
  still.height = 0;
  preview.hidden = true;
  preview.classList.remove('verified-preview');
  updateBox(null);
}

function updateBox(box, state, width, height) {
  overlay = box && width && height ? {box, state, width, height} : null;
  drawBox();
}

function drawBox() {
  faceBox.hidden = !overlay;
  preview.classList.toggle('has-face', Boolean(overlay));
  if (!overlay) return;
  const {box, state, width, height} = overlay;
  const [x, y, w, h] = box;
  const scale = Math.min(preview.clientWidth / width, preview.clientHeight / height);
  const fittedWidth = width * scale, fittedHeight = height * scale;
  faceBox.style.left = ((preview.clientWidth - fittedWidth) / 2 + (1 - x - w) * fittedWidth) + 'px';
  faceBox.style.top = ((preview.clientHeight - fittedHeight) / 2 + y * fittedHeight) + 'px';
  faceBox.style.width = (w * fittedWidth) + 'px';
  faceBox.style.height = (h * fittedHeight) + 'px';
  faceBox.className = 'face-box ' + state;
  faceBox.firstElementChild.textContent = state === 'verified'
    ? 'Face verified' : state === 'mismatch' ? 'Face does not match' : 'Checking face';
}

window.addEventListener('resize', drawBox);
window.addEventListener('pagehide', () => {
  active = false;
  generation++;
  clearTimeout(verificationTimer);
  stopCamera();
});
window.addEventListener('pageshow', event => {
  if (event.persisted) window.location.reload();
});
restart.addEventListener('click', () => window.location.reload());

login.addEventListener('submit', async event => {
  event.preventDefault();
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    message('Open the trusted HTTPS link in your phone browser to use the camera.', true);
    return;
  }
  byId('signin').disabled = true;
  message('Signing in…');
  const password = byId('password');
  // Request camera permission from the actual tap. No frames are sent before sign-in succeeds.
  const camera = requestCamera();
  camera.catch(() => {});
  try {
    const data = await send('login', JSON.stringify({
      roll: byId('roll').value.trim(), password: password.value,
    }), 'application/json');
    password.value = '';
    pose = data.pose;
    login.hidden = true;
    face.hidden = false;
    step(1);
    await runFace(camera);
  } catch (error) {
    camera.then(value => value.getTracks().forEach(track => track.stop()), () => {});
    message(error.status ? error.message : 'Connection interrupted. Try signing in again.', true);
  } finally {
    byId('signin').disabled = false;
  }
});

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

function requestCamera() {
  return navigator.mediaDevices.getUserMedia({
    video: {facingMode: {ideal: 'user'}, width: {ideal: 640}, height: {ideal: 480}},
    audio: false,
  });
}

async function cameraFrame(canvas) {
  const scale = Math.min(1, 640 / Math.max(video.videoWidth, video.videoHeight));
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', .82));
}

verify.addEventListener('click', () => runFace(requestCamera()));

async function runFace(cameraPromise) {
  const attempt = ++generation;
  verify.disabled = true;
  verify.hidden = true;
  let blocked = false;
  let verified = false;
  try {
    message('Allow camera access when your browser asks.');
    const camera = await cameraPromise;
    if (!active || attempt !== generation) {
      camera.getTracks().forEach(track => track.stop());
      return;
    }
    stream = camera;
    video.srcObject = stream;
    preview.hidden = false;
    byId('pose').hidden = false;
    byId('pose').textContent = prompts[pose];
    await video.play();
    const canvas = document.createElement('canvas');
    const deadline = performance.now() + 28000;
    while (active && attempt === generation && performance.now() < deadline) {
      if (video.readyState >= 2 && video.videoWidth && video.videoHeight) {
        const frame = await cameraFrame(canvas);
        if (frame && active && attempt === generation) {
          const data = await send('verify', frame, 'image/jpeg');
          if (!active || attempt !== generation) return;
          if (Object.hasOwn(data, 'faceBox')) {
            updateBox(data.faceBox, data.faceStatus || 'checking', canvas.width, canvas.height);
          }
          if (data.verified) {
            verified = true;
            still.width = canvas.width;
            still.height = canvas.height;
            still.getContext('2d').drawImage(canvas, 0, 0);
            still.hidden = false;
            preview.classList.add('verified-preview');
            drawBox();
            byId('complete').hidden = false;
            mark.hidden = false;
            mark.disabled = false;
            step(2);
            message('');
            verificationTimer = setTimeout(() => {
              mark.hidden = true;
              byId('complete').hidden = true;
              stopCamera();
              face.hidden = true;
              message('Face verification expired. Sign in again.', true);
              restart.hidden = false;
            }, data.validForMs);
            mark.focus();
            return;
          }
          if (data.pose) {
            pose = data.pose;
            byId('pose').textContent = prompts[pose] || prompts.center;
          }
          message(data.message, data.message.includes('does not match'));
        }
      }
      await delay(250);
    }
    if (active) message('Verification timed out. Improve the lighting and tap Verify face again.', true);
  } catch (error) {
    if (!active) return;
    blocked = [401, 403, 410].includes(error.status);
    restart.hidden = !blocked;
    if (error.name === 'NotAllowedError') {
      message('Camera permission was denied. Allow camera access in browser settings and try again.', true);
    } else if (error.name === 'NotFoundError' || error.name === 'NotReadableError') {
      message('Camera unavailable. Close other camera apps or ask your teacher for help.', true);
    } else {
      message(error.status ? error.message : 'Camera or connection interrupted. Try again.', true);
    }
  } finally {
    stopCamera(verified);
    verify.disabled = blocked;
    verify.hidden = verified || blocked;
  }
}

mark.addEventListener('click', async () => {
  mark.disabled = true;
  clearTimeout(verificationTimer);
  message('Saving attendance…');
  try {
    const data = await send('mark');
    byId('result-title').textContent = 'Attendance confirmed';
    byId('result-body').textContent = data.message;
    stopCamera();
    face.hidden = true;
    mark.hidden = true;
    message('');
  } catch (error) {
    message(error.status ? error.message : 'The save could not be confirmed. Ask your teacher to check.', true);
    restart.hidden = false;
  }
});
