function getEl(id) {
  return document.getElementById(id);
}

function resetForm() {
  getEl("categoryId").value = "";
  getEl("categoryName").value = "";
  getEl("categoryDescription").value = "";
  getEl("categoryRules").value = "";
}

function openModal() {
  getEl("modalTitle").innerText = "Add New Category";
  getEl("categoryForm").action = "/admin/categories";

  resetForm();
  showModal();
}

function openEditFromDataset(el) {
  const id = el.dataset.id || "";
  const name = el.dataset.name || "";
  const description = el.dataset.description || "";
  const rules = el.dataset.rules || "";

  console.log("EDIT CLICKED", { id, name, description, rules });

  getEl("modalTitle").innerText = "Edit Category";
  getEl("categoryForm").action = "/admin/categories";

  getEl("categoryId").value = id;
  getEl("categoryName").value = name;
  getEl("categoryDescription").value = description;
  getEl("categoryRules").value = rules;

  showModal();
}

function closeModal() {
  hideModal();
}

function showModal() {
  const modal = getEl("modal");

  modal.classList.remove("hidden");
  modal.classList.add("flex");
}

function hideModal() {
  const modal = getEl("modal");

  modal.classList.add("hidden");
  modal.classList.remove("flex");

  resetForm();
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") hideModal();
});
