// ベンチマークのショート動画の「音の特徴」を、再生しながら数字で記録する（Chrome で、そのページを開いた状態で実行）。
// 動画や音そのものは保存しない。記録するのは 30ミリ秒ごとの 音の大きさ・高さの帯ごとの強さ・声の高さ だけ。
// 終わると「<動画ID>_oto.json」がダウンロードされる。
(async () => {
  const v = [...document.querySelectorAll('video')].find((x) => x.offsetWidth > 0) || document.querySelector('video');
  if (!v) return alert('動画が見つかりません');
  const id = (location.pathname.match(/shorts\/([\w-]{11})/) || location.search.match(/v=([\w-]{11})/) || [])[1] || 'video';
  v.pause(); v.loop = false; v.muted = false; v.volume = 1; v.currentTime = 0;
  const ctx = new AudioContext();
  const src = ctx.createMediaElementSource(v);
  const an = ctx.createAnalyser(); an.fftSize = 4096; an.smoothingTimeConstant = 0;
  src.connect(an); an.connect(ctx.destination);
  const sr = ctx.sampleRate, N = an.fftSize;
  const td = new Float32Array(N), fd = new Float32Array(an.frequencyBinCount);
  const bands = [[50, 300], [300, 1000], [1000, 3000], [3000, 6000], [6000, 12000]];
  const binOf = (f) => Math.round((f * N) / sr);
  const pitch = () => { // 70〜600Hz の自己相関で声の高さ
    let best = 0, lag = 0;
    for (let L = Math.floor(sr / 600); L <= Math.floor(sr / 70); L++) {
      let s = 0; for (let i = 0; i < N - L; i += 2) s += td[i] * td[i + L];
      if (s > best) { best = s; lag = L; }
    }
    let e = 0; for (let i = 0; i < N; i += 2) e += td[i] * td[i];
    return e > 0 && best / e > 0.3 ? Math.round(sr / lag) : 0;
  };
  const rows = []; let last = -1;
  await ctx.resume(); await v.play();
  await new Promise((res) => {
    const iv = setInterval(() => {
      const t = v.currentTime;
      if (t < last - 1 || v.ended) { clearInterval(iv); return res(); } // 1周したら終わり
      last = t;
      an.getFloatTimeDomainData(td); an.getFloatFrequencyData(fd);
      let s = 0; for (const x of td) s += x * x;
      const rms = Math.sqrt(s / N);
      let num = 0, den = 0;
      const be = bands.map(([a, b]) => { let p = 0; for (let i = binOf(a); i < binOf(b); i++) p += Math.pow(10, fd[i] / 10); return +(10 * Math.log10(p + 1e-12)).toFixed(1); });
      for (let i = 1; i < fd.length; i++) { const m = Math.pow(10, fd[i] / 20); num += m * (i * sr) / N; den += m; }
      rows.push([+t.toFixed(3), +rms.toFixed(4), Math.round(num / (den || 1)), pitch(), ...be]);
    }, 30);
  });
  v.pause();
  const out = { id, url: location.href, duration: v.duration, sampleRate: sr, cols: ['t', 'rms', 'centroid', 'pitch', 'b50_300', 'b300_1k', 'b1k_3k', 'b3k_6k', 'b6k_12k'], rows };
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out)], { type: 'application/json' }));
  a.download = `${id}_oto.json`; a.click();
  return `記録しました：${rows.length}行（${v.duration.toFixed(1)}秒）`;
})();
