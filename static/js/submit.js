const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const preview = document.getElementById("imagePreview");

// Guard clause (prevents silent crashes if DOM changes)
if (dropzone && fileInput && preview) {
  function showPreview(file) {
    if (!file) return;

    const url = URL.createObjectURL(file);
    preview.src = url;
    preview.classList.remove("hidden");
  }

  // Click to open file picker
  dropzone.addEventListener("click", () => {
    fileInput.click();
  });

  // File selected normally
  fileInput.addEventListener("change", function () {
    const file = this.files[0];
    showPreview(file);
  });

  // Drag over
  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("border-neutral-500");
  });

  // Drag leave
  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("border-neutral-500");
  });

  // Drop file
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("border-neutral-500");

    const file = e.dataTransfer.files[0];

    // Sync file input (important for form submit)
    fileInput.files = e.dataTransfer.files;

    showPreview(file);
  });
}
