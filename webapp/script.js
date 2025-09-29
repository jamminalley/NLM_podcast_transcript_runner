const audioInput = document.getElementById("audioInput");
const vttInput = document.getElementById("vttInput");
const translationToggle = document.getElementById("translationToggle");
const audioPlayer = document.getElementById("audioPlayer");
const transcriptContainer = document.getElementById("transcript");
const cueTemplate = document.getElementById("cueTemplate");

let cues = [];
let activeCueIndex = -1;

audioInput.addEventListener("change", handleAudioSelection);
vttInput.addEventListener("change", handleVttSelection);
audioPlayer.addEventListener("timeupdate", handleTimeUpdate);
audioPlayer.addEventListener("seeking", () => updateActiveCue(audioPlayer.currentTime, true));
translationToggle.addEventListener("change", handleTranslationToggle);

function handleAudioSelection(event) {
  const [file] = event.target.files;
  if (!file) return;
  const url = URL.createObjectURL(file);
  audioPlayer.src = url;
  audioPlayer.load();
}

async function handleVttSelection(event) {
  const [file] = event.target.files;
  if (!file) return;
  const text = await file.text();
  cues = parseVtt(text);
  renderTranscript(cues);
  activeCueIndex = -1;
  updateActiveCue(audioPlayer.currentTime, true);
}

function handleTranslationToggle(event) {
  transcriptContainer.classList.toggle("hide-translation", !event.target.checked);
}

function parseVtt(content) {
  const lines = content.split(/\r?\n/);
  const parsedCues = [];
  let i = 0;

  while (i < lines.length) {
    let line = lines[i].trim();
    if (!line) {
      i += 1;
      continue;
    }

    // Identifier (optional)
    let identifier = null;
    if (!line.includes("-->")) {
      identifier = line;
      i += 1;
      line = lines[i]?.trim() ?? "";
    }

    const timeMatch = line.match(/(?<start>[0-9:.]+)\s*-->\s*(?<end>[0-9:.]+)/);
    if (!timeMatch) {
      i += 1;
      continue;
    }

    const start = parseTimestamp(timeMatch.groups.start);
    const end = parseTimestamp(timeMatch.groups.end);
    const textLines = [];
    i += 1;

    while (i < lines.length && lines[i].trim() !== "") {
      textLines.push(lines[i]);
      i += 1;
    }

    const html = textLines.join("\n");
    parsedCues.push({ identifier, start, end, html });
  }

  return parsedCues;
}

function parseTimestamp(value) {
  const [hh, mm, rest] = value.split(":");
  const [ss, ms = "0"] = rest.split(".");
  return parseInt(hh, 10) * 3600 + parseInt(mm, 10) * 60 + parseInt(ss, 10) + parseInt(ms, 10) / 1000;
}

function renderTranscript(cues) {
  transcriptContainer.innerHTML = "";
  cues.forEach((cue, index) => {
    const node = cueTemplate.content.firstElementChild.cloneNode(true);
    node.dataset.start = cue.start;
    node.dataset.end = cue.end;
    node.dataset.index = index;

    const wrapper = document.createElement("div");
    wrapper.innerHTML = cue.html;

    const ptElement = node.querySelector(".pt");
    const enElement = node.querySelector(".en");

    const ptSource = wrapper.querySelector(".pt") || wrapper.firstElementChild;
    const enSource = wrapper.querySelector(".en");

    if (ptSource) {
      ptElement.innerHTML = ptSource.innerHTML || ptSource.textContent || "";
    }
    if (enSource) {
      enElement.innerHTML = enSource.innerHTML || enSource.textContent || "";
    } else {
      enElement.remove();
    }

    node.addEventListener("click", () => {
      audioPlayer.currentTime = cue.start + 0.01;
      audioPlayer.play();
    });

    transcriptContainer.appendChild(node);
  });
}

function handleTimeUpdate() {
  if (!cues.length) return;
  updateActiveCue(audioPlayer.currentTime, false);
}

function updateActiveCue(currentTime, seeking) {
  if (!cues.length) return;

  const index = cues.findIndex((cue, idx) => {
    if (idx < activeCueIndex) return false;
    return currentTime >= cue.start && currentTime < cue.end + 0.05;
  });

  if (index === -1) {
    if (currentTime < cues[0].start) {
      setActiveCue(-1);
    } else if (currentTime >= cues[cues.length - 1].end) {
      setActiveCue(cues.length - 1);
    }
    return;
  }

  setActiveCue(index, seeking);
}

function setActiveCue(index, seeking = false) {
  if (index === activeCueIndex) return;
  const previous = transcriptContainer.querySelector(".cue.active");
  if (previous) {
    previous.classList.remove("active");
  }

  activeCueIndex = index;
  if (index === -1) return;
  const current = transcriptContainer.querySelector(`.cue[data-index="${index}"]`);
  if (!current) return;
  current.classList.add("active");

  if (!seeking) {
    current.scrollIntoView({ behavior: "smooth", block: "center" });
  } else {
    current.scrollIntoView({ behavior: "instant", block: "center" });
  }
}

handleTranslationToggle({ target: translationToggle });
