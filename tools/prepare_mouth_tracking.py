"""Track the tiny mouth in the pinned dsh-pet clips, without runtime CV dependencies."""
from pathlib import Path
import hashlib
import json
import math
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'static/assets/dsh-pet'
WIDTH, HEIGHT = 640, 360


def components(points):
    points = set(points)
    while points:
        first = points.pop()
        stack, group = [first], [first]
        while stack:
            x, y = stack.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    p = (x + dx, y + dy)
                    if p in points:
                        points.remove(p)
                        group.append(p)
                        stack.append(p)
        yield group


def track_frame(frame, previous):
    def pixel(x, y):
        offset = (y * WIDTH + x) * 4
        return frame[offset:offset + 3]
    points = []
    center_x, center_y = previous[:2]
    for y in range(max(194, round(center_y)-6), min(217, round(center_y)+7)):
        left_skin = pixel(round(center_x)-13, y)
        right_skin = pixel(round(center_x)+13, y)
        if min(left_skin[0], right_skin[0]) < 220:
            continue
        background_g = (left_skin[1]+right_skin[1])/2
        for x in range(round(center_x)-10, round(center_x)+11):
            r, g, b = pixel(x, y)
            if g < background_g-7 and r > b*1.03 and r > 80:
                points.append((x, y))
    candidates = []
    for group in components(points):
        xs, ys = zip(*group)
        left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
        w, h = right-left+1, bottom-top+1
        x, y = (left+right)/2, (top+bottom)/2
        if w <= 21 and h <= 13 and 195 <= y <= 213 and len(group) >= 2:
            distance = math.hypot(x-previous[0], y-previous[1])
            candidates.append((distance, x, y, w, h))
    if not candidates:
        raise ValueError('Mouth not located')
    _, x, y, w, h = min(candidates)
    colors = []
    for px in (round(x-w/2-3), round(x+w/2+3)):
        for py in range(round(y)-1, round(y)+2):
            rgb = pixel(px, py)
            if rgb[0] > 220 and rgb[1] > 170:
                colors.append(rgb)
    if not colors:
        raise ValueError('No clean skin sample')
    color = [round(sum(v[c] for v in colors)/len(colors)) for c in range(3)]
    return [x, y, round(w/2+1.8, 2), round(h/2+1.5, 2), *color]


def main():
    result = {'fps': 24, 'width': WIDTH, 'height': HEIGHT,
              'license': 'CC-BY-NC-SA-4.0', 'clips': {}, 'source_sha256': {}}
    originals = {item['file']: item for item in json.loads((ASSETS / 'manifest.json').read_text())['assets']}
    for clip in ('speaking',):
        path = ASSETS / f'{clip}.webm'
        if hashlib.sha256(path.read_bytes()).hexdigest() != originals[path.name]['sha256']:
            raise ValueError('Upstream checksum mismatch')
        process = subprocess.Popen(['ffmpeg', '-v', 'error', '-c:v', 'libvpx-vp9', '-i', str(path),
                                    '-pix_fmt', 'rgba', '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
        frames, previous = [], [312, 202]
        try:
            while frame := process.stdout.read(WIDTH * HEIGHT * 4):
                if len(frame) != WIDTH * HEIGHT * 4:
                    raise ValueError('Incomplete frame')
                tracking = track_frame(frame, previous)
                if math.dist(tracking[:2], previous[:2]) > 5:
                    raise ValueError(f'Unexpected mouth jump at frame {len(frames)}: {tracking}')
                frames.append(tracking)
                previous = tracking
            if process.wait() != 0 or len(frames) != 241:
                raise ValueError('Unexpected clip length')
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                process.wait()
        result['clips'][clip] = frames
        result['source_sha256'][clip] = hashlib.sha256(path.read_bytes()).hexdigest()
        print(clip, len(frames), 'x', min(f[0] for f in frames), max(f[0] for f in frames),
              'y', min(f[1] for f in frames), max(f[1] for f in frames))
    (ASSETS / 'mouth-tracking.json').write_text(json.dumps(result, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
