/**
 * script.js — Quran Reels Maker: Client-Side Execution Controller
 * ================================================================
 * Responsibilities:
 *   - Particle canvas background animation
 *   - Radio card interactivity
 *   - Form validation before submission
 *   - Async fetch to /generate endpoint
 *   - Progress bar animation with phase descriptions
 *   - Video preview reveal on success
 *   - Error display with retry support
 */

"use strict";

/* ═══════════════════════════════════════════════════════════════════════════
   SECTION 1 — CONSTANTS & STATE
═══════════════════════════════════════════════════════════════════════════ */

/** All human-readable phase messages shown during generation. */
const PHASE_MESSAGES = [
  "Connecting to Quran API and fetching verse text...",
  "Applying Arabic reshaping and BiDi rendering pipeline...",
  "Downloading recitation audio from EveryAyah servers...",
  "Querying Pexels API for Surah-themed background video...",
  "Streaming and saving background video to temp storage...",
  "Building ambient soundscape overlay and mixing audio...",
  "Compositing video layers: background, dimming, and text...",
  "Encoding final MP4 with H.264 + AAC (this may take a while)...",
  "Finalising output file and verifying render integrity...",
  "Reel ready! Loading preview...",
];

/**
 * Progress percentages mapped to each pipeline step shown in the UI.
 * Index 0 = Step 1 (Fetch Verses), Index 4 = Step 5 (Complete).
 */
const STEP_THRESHOLDS = [10, 30, 55, 80, 100];

/** Interval handle for the progress animation ticker. */
let progressIntervalId = null;

/** Current simulated progress value (0–99). Capped until server responds. */
let currentProgress = 0;

/** Whether a generation request is currently in flight. */
let isGenerating = false;

/* ═══════════════════════════════════════════════════════════════════════════
   SECTION 2 — DOM ELEMENT REFERENCES
═══════════════════════════════════════════════════════════════════════════ */

/** @type {HTMLFormElement} */
const reelForm = document.getElementById("reelForm");

/** @type {HTMLButtonElement} */
const generateBtn = document.getElementById("generateBtn");

/** @type {HTMLInputElement} */
const surahInput = document.getElementById("surahInput");

/** @type {HTMLInputElement} */
const startAyahInput = document.getElementById("startAyahInput");

/** @type {HTMLInputElement} */
const endAyahInput = document.getElementById("endAyahInput");

/** @type {HTMLSelectElement} */
const reciterSelect = document.getElementById("reciterSelect");

/** @type {HTMLInputElement} */
const webhookInput = document.getElementById("webhookInput");

/** @type {HTMLElement} */
const progressSection = document.getElementById("progressSection");

/** @type {HTMLElement} */
const progressBarFill = document.getElementById("progressBarFill");

/** @type {HTMLElement} */
const progressStatusText = document.getElementById("progressStatusText");

/** @type {HTMLElement} */
const phaseText = document.getElementById("phaseText");

/** @type {HTMLElement} */
const previewSection = document.getElementById("previewSection");

/** @type {HTMLVideoElement} */
const reelVideoPlayer = document.getElementById("reelVideoPlayer");

/** @type {HTMLAnchorElement} */
const downloadLink = document.getElementById("downloadLink");

/** @type {HTMLButtonElement} */
const generateAnotherBtn = document.getElementById("generateAnotherBtn");

/** @type {HTMLElement} */
const errorSection = document.getElementById("errorSection");

/** @type {HTMLElement} */
const errorMessageText = document.getElementById("errorMessageText");

/** @type {HTMLButtonElement} */
const retryBtn = document.getElementById("retryBtn");

/** @type {HTMLCanvasElement} */
const particleCanvas = document.getElementById("particleCanvas");

/* ═══════════════════════════════════════════════════════════════════════════
   SECTION 3 — PARTICLE CANVAS BACKGROUND
═══════════════════════════════════════════════════════════════════════════ */

/**
 * Initialise and animate the starfield particle canvas that renders behind
 * the entire application layout.
 */
function initParticleCanvas() {
  if (!particleCanvas) return;

  const ctx = particleCanvas.getContext("2d");
  if (!ctx) return;

  /** @type {{ x: number, y: number, r: number, speed: number, opacity: number, pulse: number }[]} */
  const particles = [];
  const PARTICLE_COUNT = 90;

  /** Resize canvas to match window dimensions. */
  function resizeCanvas() {
    particleCanvas.width = window.innerWidth;
    particleCanvas.height = window.innerHeight;
  }

  /** Populate the particles array with randomised initial values. */
  function createParticles() {
    particles.length = 0;
    for (let index = 0; index < PARTICLE_COUNT; index++) {
      particles.push({
        x: Math.random() * particleCanvas.width,
        y: Math.random() * particleCanvas.height,
        r: Math.random() * 1.4 + 0.3,
        speed: Math.random() * 0.18 + 0.04,
        opacity: Math.random() * 0.5 + 0.1,
        pulse: Math.random() * Math.PI * 2,
      });
    }
  }

  /** Draw a single animation frame. */
  function drawFrame() {
    ctx.clearRect(0, 0, particleCanvas.width, particleCanvas.height);

    const now = Date.now() * 0.001;

    for (let index = 0; index < particles.length; index++) {
      const particle = particles[index];

      // Drift upward slowly and wrap around the top edge
      particle.y -= particle.speed;
      if (particle.y + particle.r < 0) {
        particle.y = particleCanvas.height + particle.r;
        particle.x = Math.random() * particleCanvas.width;
      }

      // Gentle sinusoidal horizontal drift
      particle.x += Math.sin(now * 0.3 + particle.pulse) * 0.12;

      // Pulsing opacity
      const dynamicOpacity =
        particle.opacity * (0.6 + 0.4 * Math.sin(now * 0.8 + particle.pulse));

      ctx.beginPath();
      ctx.arc(particle.x, particle.y, particle.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(212, 175, 55, ${dynamicOpacity})`;
      ctx.fill();
    }

    requestAnimationFrame(drawFrame);
  }

  resizeCanvas();
  createParticles();
  drawFrame();

  window.addEventListener("resize", () => {
    resizeCanvas();
    createParticles();
  });
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECTION 4 — RADIO CARD INTERACTIVITY
═══════════════════════════════════════════════════════════════════════════ */

/**
 * Wire up the ambient effect radio cards so that clicking a card visually
 * activates it by toggling the `radio-card--active` CSS class.
 */
function initRadioCards() {
  const allRadioCards = document.querySelectorAll(".radio-card");
  const allRadioInputs = document.querySelectorAll(".radio-input");

  allRadioCards.forEach(function (card) {
    card.addEventListener("click", function () {
      // Remove active state from all cards
      allRadioCards.forEach(function (otherCard) {
        otherCard.classList.remove("radio-card--active");
      });

      // Activate the clicked card
      card.classList.add("radio-card--active");
    });

    // Also handle keyboard activation (Enter / Space)
    card.addEventListener("keydown", function (keyboardEvent) {
      if (keyboardEvent.key === "Enter" || keyboardEvent.key === " ") {
        keyboardEvent.preventDefault();
        card.click();
      }
    });
  });

  // Sync visual state when radio input is changed programmatically
  allRadioInputs.forEach(function (radioInput) {
    radioInput.addEventListener("change", function () {
      if (radioInput.checked) {
        allRadioCards.forEach(function (otherCard) {
          otherCard.classList.remove("radio-card--active");
        });
        const parentCard = radioInput.closest(".radio-card");
        if (parentCard) {
          parentCard.classList.add("radio-card--active");
        }
      }
    });
  });
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECTION 5 — FORM VALIDATION
═══════════════════════════════════════════════════════════════════════════ */

/**
 * Validate all required form fields before submission.
 * Returns an object with { valid: boolean, message: string }.
 *
 * @returns {{ valid: boolean, message: string }}
 */
function validateForm() {
  const surahValue = parseInt(surahInput.value, 10);
  const startAyahValue = parseInt(startAyahInput.value, 10);
  const endAyahValue = parseInt(endAyahInput.value, 10);
  const webhookValue = webhookInput.value.trim();

  // Clear previous error states
  surahInput.classList.remove("input-field--error");
  startAyahInput.classList.remove("input-field--error");
  endAyahInput.classList.remove("input-field--error");
  webhookInput.classList.remove("input-field--error");

  if (isNaN(surahValue) || surahValue < 1 || surahValue > 114) {
    surahInput.classList.add("input-field--error");
    surahInput.focus();
    return {
      valid: false,
      message: "Surah number must be between 1 and 114.",
    };
  }

  if (isNaN(startAyahValue) || startAyahValue < 1) {
    startAyahInput.classList.add("input-field--error");
    startAyahInput.focus();
    return {
      valid: false,
      message: "Starting Ayah must be 1 or greater.",
    };
  }

  if (isNaN(endAyahValue) || endAyahValue < startAyahValue) {
    endAyahInput.classList.add("input-field--error");
    endAyahInput.focus();
    return {
      valid: false,
      message: "Ending Ayah must be equal to or greater than Starting Ayah.",
    };
  }

  const totalAyahs = endAyahValue - startAyahValue + 1;
  if (totalAyahs > 20) {
    endAyahInput.classList.add("input-field--error");
    endAyahInput.focus();
    return {
      valid: false,
      message:
        "Maximum 20 Ayahs per reel. Reduce the range (End Ayah − Start Ayah ≤ 19).",
    };
  }

  if (webhookValue.length > 0) {
    try {
      new URL(webhookValue);
    } catch (_urlError) {
      webhookInput.classList.add("input-field--error");
      webhookInput.focus();
      return {
        valid: false,
        message:
          "Webhook URL is not a valid URL. Leave blank to skip publishing.",
      };
    }
  }

  return { valid: true, message: "" };
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECTION 6 — PROGRESS BAR ANIMATION
═══════════════════════════════════════════════════════════════════════════ */

/**
 * Start the simulated progress bar animation.
 * The bar advances automatically but is deliberately slowed near 90%
 * to wait for the real server response before reaching 100%.
 */
function startProgressAnimation() {
  currentProgress = 0;
  let phaseIndex = 0;
  let lastPhaseChangeProgress = 0;

  updateProgressBar(0);
  updatePhaseText(PHASE_MESSAGES[0]);
  updateProgressSteps(0);

  progressIntervalId = setInterval(function () {
    if (!isGenerating) {
      clearInterval(progressIntervalId);
      progressIntervalId = null;
      return;
    }

    // Advance speed is fast at start, slows down as we approach 90%
    let increment;
    if (currentProgress < 20) {
      increment = 1.2;
    } else if (currentProgress < 45) {
      increment = 0.7;
    } else if (currentProgress < 70) {
      increment = 0.4;
    } else if (currentProgress < 88) {
      increment = 0.18;
    } else {
      // Hold near 90% waiting for real server response
      increment = 0;
    }

    currentProgress = Math.min(currentProgress + increment, 90);
    updateProgressBar(currentProgress);

    // Advance phase message every ~12% of progress
    const progressSinceLastPhase = currentProgress - lastPhaseChangeProgress;
    if (
      progressSinceLastPhase >= 12 &&
      phaseIndex < PHASE_MESSAGES.length - 1
    ) {
      phaseIndex++;
      lastPhaseChangeProgress = currentProgress;
      updatePhaseText(PHASE_MESSAGES[phaseIndex]);
    }

    // Determine which step indicator to highlight
    const activeStep = STEP_THRESHOLDS.findIndex(function (threshold) {
      return currentProgress < threshold;
    });
    updateProgressSteps(activeStep === -1 ? 4 : activeStep);

  }, 120);
}

/**
 * Stop the simulated progress animation and jump the bar to 100%.
 */
function completeProgressAnimation() {
  if (progressIntervalId !== null) {
    clearInterval(progressIntervalId);
    progressIntervalId = null;
  }
  currentProgress = 100;
  updateProgressBar(100);
  updatePhaseText(PHASE_MESSAGES[PHASE_MESSAGES.length - 1]);
  updateProgressSteps(4);
}

/**
 * Stop the simulated progress animation without completing (on error).
 */
function stopProgressAnimation() {
  if (progressIntervalId !== null) {
    clearInterval(progressIntervalId);
    progressIntervalId = null;
  }
}

/**
 * Update the visual width of the progress bar fill element.
 *
 * @param {number} percent - Value from 0 to 100.
 */
function updateProgressBar(percent) {
  const clampedPercent = Math.max(0, Math.min(100, percent));
  progressBarFill.style.width = clampedPercent + "%";

  const progressBarContainer = progressBarFill.closest(
    "[role='progressbar']"
  );
  if (progressBarContainer) {
    progressBarContainer.setAttribute(
      "aria-valuenow",
      Math.round(clampedPercent)
    );
  }

  progressStatusText.textContent =
    Math.round(clampedPercent) + "% complete";
}

/**
 * Animate a phase message change with a fade transition.
 *
 * @param {string} message - The new phase description to display.
 */
function updatePhaseText(message) {
  phaseText.classList.remove("phase-item--active");

  setTimeout(function () {
    phaseText.textContent = "";

    const iconSpan = document.createElement("span");
    iconSpan.className = "phase-icon";
    iconSpan.setAttribute("aria-hidden", "true");
    iconSpan.textContent = "✦";

    const textNode = document.createTextNode(" " + message);

    phaseText.appendChild(iconSpan);
    phaseText.appendChild(textNode);

    phaseText.classList.add("phase-item--active");
  }, 180);
}

/**
 * Update the step indicator dots — marking steps as done or active.
 *
 * @param {number} activeStepIndex - Zero-based index of the currently active step.
 */
function updateProgressSteps(activeStepIndex) {
  const stepElements = document.querySelectorAll(".progress-step");

  stepElements.forEach(function (stepElement, index) {
    stepElement.classList.remove("step--active", "step--done");

    if (index < activeStepIndex) {
      stepElement.classList.add("step--done");
    } else if (index === activeStepIndex) {
      stepElement.classList.add("step--active");
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECTION 7 — UI SECTION VISIBILITY HELPERS
═══════════════════════════════════════════════════════════════════════════ */

/**
 * Show the progress section and hide preview/error panels.
 */
function showProgressSection() {
  progressSection.removeAttribute("hidden");
  previewSection.setAttribute("hidden", "");
  errorSection.setAttribute("hidden", "");

  progressSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

/**
 * Show the video preview section with the provided output path.
 *
 * @param {string} outputPath - Relative path to the rendered video file.
 */
function showPreviewSection(outputPath) {
  const videoUrl = "/" + outputPath;

  reelVideoPlayer.src = videoUrl;
  reelVideoPlayer.load();

  downloadLink.href = videoUrl;
  downloadLink.download = outputPath.split("/").pop() || "quran_reel.mp4";

  progressSection.setAttribute("hidden", "");
  previewSection.removeAttribute("hidden");
  errorSection.setAttribute("hidden", "");

  previewSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

/**
 * Show the error section with an explanatory message.
 *
 * @param {string} message - Human-readable error description.
 */
function showErrorSection(message) {
  errorMessageText.textContent =
    message || "An unknown error occurred. Check the server logs for details.";

  progressSection.setAttribute("hidden", "");
  previewSection.setAttribute("hidden", "");
  errorSection.removeAttribute("hidden");

  errorSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

/**
 * Reset the generate button to its default enabled state.
 */
function resetGenerateButton() {
  generateBtn.disabled = false;
  const btnTextSpan = generateBtn.querySelector(".btn-text");
  if (btnTextSpan) {
    btnTextSpan.textContent = "Generate Reel";
  }
}

/**
 * Set the generate button to a loading/disabled state.
 */
function setGenerateButtonLoading() {
  generateBtn.disabled = true;
  const btnTextSpan = generateBtn.querySelector(".btn-text");
  if (btnTextSpan) {
    btnTextSpan.textContent = "Generating…";
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECTION 8 — FORM SUBMISSION & FETCH API
═══════════════════════════════════════════════════════════════════════════ */

/**
 * Read all current form values and assemble the request payload object.
 *
 * @returns {{ surah: number, start_ayah: number, end_ayah: number, reciter: string, effect: string, webhook_url: string }}
 */
function collectFormPayload() {
  const selectedEffectInput = document.querySelector(
    'input[name="effect"]:checked'
  );
  const selectedEffect = selectedEffectInput
    ? selectedEffectInput.value
    : "None";

  return {
    surah: parseInt(surahInput.value, 10),
    start_ayah: parseInt(startAyahInput.value, 10),
    end_ayah: parseInt(endAyahInput.value, 10),
    reciter: reciterSelect.value,
    effect: selectedEffect,
    webhook_url: webhookInput.value.trim(),
  };
}

/**
 * Submit the generation request to the Flask /generate endpoint.
 * Handles the full lifecycle: validation → loading state → fetch → result.
 *
 * @param {Event} submitEvent - The form submit event (prevented from default).
 */
async function handleFormSubmit(submitEvent) {
  submitEvent.preventDefault();

  if (isGenerating) {
    console.warn("[script.js] Generation already in progress. Ignoring duplicate submit.");
    return;
  }

  // ── Step 1: Validate form inputs ───────────────────────────────────────
  const validationResult = validateForm();
  if (!validationResult.valid) {
    showErrorSection(validationResult.message);
    return;
  }

  // ── Step 2: Assemble payload ────────────────────────────────────────────
  const requestPayload = collectFormPayload();

  console.info(
    "[script.js] Submitting generation request:",
    JSON.stringify(requestPayload)
  );

  // ── Step 3: Enter loading state ─────────────────────────────────────────
  isGenerating = true;
  setGenerateButtonLoading();
  showProgressSection();
  startProgressAnimation();

  // ── Step 4: Send fetch request ──────────────────────────────────────────
  let responseData = null;

  try {
    const fetchResponse = await fetch("/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(requestPayload),
    });

    let rawJson = null;

    try {
      rawJson = await fetchResponse.json();
    } catch (jsonParseError) {
      console.error(
        "[script.js] Server returned non-JSON body.",
        jsonParseError
      );
      throw new Error(
        "Server returned an unreadable response (HTTP " +
          fetchResponse.status +
          "). Check server logs."
      );
    }

    responseData = rawJson;

    if (!fetchResponse.ok) {
      const serverMessage =
        responseData && responseData.message
          ? responseData.message
          : "Server error (HTTP " + fetchResponse.status + ").";
      throw new Error(serverMessage);
    }

  } catch (networkOrServerError) {
    // ── Network failure or server error ────────────────────────────────
    console.error(
      "[script.js] Generation request failed:",
      networkOrServerError
    );

    stopProgressAnimation();
    isGenerating = false;
    resetGenerateButton();

    showErrorSection(
      networkOrServerError.message ||
        "Network error — could not reach the generation server. " +
        "Ensure the Flask server is running on port 5000."
    );
    return;
  }

  // ── Step 5: Handle server response ─────────────────────────────────────
  isGenerating = false;
  resetGenerateButton();

  if (responseData && responseData.success === true) {
    console.info(
      "[script.js] Generation succeeded. Output path:",
      responseData.output_path
    );

    completeProgressAnimation();

    // Brief pause so the user sees 100% before the preview appears
    setTimeout(function () {
      showPreviewSection(responseData.output_path);
    }, 700);

  } else {
    const failureMessage =
      responseData && responseData.message
        ? responseData.message
        : "Generation failed for an unknown reason.";

    console.warn("[script.js] Server reported failure:", failureMessage);

    stopProgressAnimation();
    showErrorSection(failureMessage);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECTION 9 — SECONDARY EVENT LISTENERS
═══════════════════════════════════════════════════════════════════════════ */

/**
 * Reset the entire UI back to the form view so the user can create another
 * reel without reloading the page.
 */
function handleGenerateAnother() {
  // Hide result panels
  previewSection.setAttribute("hidden", "");
  errorSection.setAttribute("hidden", "");
  progressSection.setAttribute("hidden", "");

  // Pause and unload the video player to free memory
  reelVideoPlayer.pause();
  reelVideoPlayer.removeAttribute("src");
  reelVideoPlayer.load();

  // Reset progress bar visual state
  updateProgressBar(0);
  updateProgressSteps(0);

  // Scroll back to the form
  reelForm.scrollIntoView({ behavior: "smooth", block: "start" });

  // Re-focus the first input for accessibility
  setTimeout(function () {
    surahInput.focus();
  }, 400);
}

/**
 * Handle the retry button — re-submits the form with the same values.
 */
function handleRetry() {
  errorSection.setAttribute("hidden", "");
  reelForm.dispatchEvent(new Event("submit", { cancelable: true }));
}

/**
 * Validate numeric range inputs on blur so the user gets instant feedback
 * without waiting for form submission.
 *
 * @param {FocusEvent} blurEvent
 */
function handleNumericInputBlur(blurEvent) {
  const inputElement = blurEvent.target;
  const rawValue = inputElement.value.trim();

  if (rawValue === "") return;

  const numericValue = parseInt(rawValue, 10);
  const minValue = parseInt(inputElement.getAttribute("min"), 10);
  const maxValue = parseInt(inputElement.getAttribute("max"), 10);

  if (
    isNaN(numericValue) ||
    numericValue < minValue ||
    numericValue > maxValue
  ) {
    inputElement.classList.add("input-field--error");
  } else {
    inputElement.classList.remove("input-field--error");
  }
}

/**
 * Remove error state when the user starts correcting an input.
 *
 * @param {InputEvent} inputEvent
 */
function handleInputChange(inputEvent) {
  inputEvent.target.classList.remove("input-field--error");

  // Also hide the error section if visible, so stale errors disappear
  if (!errorSection.hasAttribute("hidden")) {
    errorSection.setAttribute("hidden", "");
  }
}

/**
 * Ensure end_ayah is always >= start_ayah as the user types.
 */
function handleStartAyahChange() {
  const startValue = parseInt(startAyahInput.value, 10);
  const endValue = parseInt(endAyahInput.value, 10);

  if (!isNaN(startValue) && !isNaN(endValue) && endValue < startValue) {
    endAyahInput.value = startAyahInput.value;
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECTION 10 — KEYBOARD & ACCESSIBILITY UTILITIES
═══════════════════════════════════════════════════════════════════════════ */

/**
 * Allow pressing Enter on the surah / ayah inputs to jump focus to the next
 * logical input field for faster mobile keyboard navigation.
 *
 * @param {KeyboardEvent} keyboardEvent
 */
function handleInputEnterKey(keyboardEvent) {
  if (keyboardEvent.key !== "Enter") return;

  const focusOrder = [
    surahInput,
    startAyahInput,
    endAyahInput,
    reciterSelect,
    webhookInput,
  ];

  const currentIndex = focusOrder.indexOf(keyboardEvent.target);
  if (currentIndex !== -1 && currentIndex < focusOrder.length - 1) {
    keyboardEvent.preventDefault();
    focusOrder[currentIndex + 1].focus();
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECTION 11 — VIDEO PLAYER HELPERS
═══════════════════════════════════════════════════════════════════════════ */

/**
 * Handle video load errors — show a fallback message inside the preview panel
 * instead of a silent broken player.
 */
function handleVideoError() {
  console.error(
    "[script.js] Video player error — file may still be processing " +
    "or the path is unreachable."
  );

  const videoContainer = reelVideoPlayer.closest(".video-container");
  if (videoContainer) {
    videoContainer.innerHTML =
      '<p style="color:#8a8d9e;font-size:0.8125rem;padding:2rem;text-align:center;">' +
      "Video preview unavailable — use the Download button to save the file." +
      "</p>";
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECTION 12 — INITIALISATION
═══════════════════════════════════════════════════════════════════════════ */

/**
 * Bind all event listeners and initialise subsystems.
 * Called once the DOM is fully loaded.
 */
function init() {
  // Particle background
  initParticleCanvas();

  // Radio card visual interactivity
  initRadioCards();

  // Primary form submit handler
  if (reelForm) {
    reelForm.addEventListener("submit", handleFormSubmit);
  }

  // Numeric field blur validation
  [surahInput, startAyahInput, endAyahInput].forEach(function (inputEl) {
    if (inputEl) {
      inputEl.addEventListener("blur", handleNumericInputBlur);
      inputEl.addEventListener("input", handleInputChange);
      inputEl.addEventListener("keydown", handleInputEnterKey);
    }
  });

  // Auto-correct end_ayah when start_ayah changes
  if (startAyahInput) {
    startAyahInput.addEventListener("change", handleStartAyahChange);
  }

  // Clear error styling on webhook input change
  if (webhookInput) {
    webhookInput.addEventListener("input", handleInputChange);
  }

  // "Make Another" button in preview section
  if (generateAnotherBtn) {
    generateAnotherBtn.addEventListener("click", handleGenerateAnother);
  }

  // Retry button in error section
  if (retryBtn) {
    retryBtn.addEventListener("click", handleRetry);
  }

  // Video player error handler
  if (reelVideoPlayer) {
    reelVideoPlayer.addEventListener("error", handleVideoError);
  }

  console.info(
    "[script.js] Quran Reels Maker client initialised successfully."
  );
}

// Entry point — wait for full DOM parse before wiring up listeners
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
    }
