document.addEventListener("click", function (e) {
  const toggle = e.target.closest("[data-menu-toggle]");
  const menus = document.querySelectorAll("[data-menu]");

  if (toggle) {
    e.stopPropagation();
    const menu = toggle.nextElementSibling;

    menus.forEach((m) => {
      if (m !== menu) m.classList.add("hidden");
    });

    if (menu) {
      menu.classList.toggle("hidden");
    }

    return;
  }

  menus.forEach((menu) => menu.classList.add("hidden"));
});

document.querySelectorAll(".vote-form").forEach((form) => {
  const postId = form.dataset.postId;
  const countEl = form.querySelector(".vote-count");

  form.querySelectorAll(".vote-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      const value = button.dataset.value;

      try {
        const res = await fetch(form.action, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "fetch",
          },
          body: JSON.stringify({ value }),
        });

        if (!res.ok) return;

        let data;

        try {
          data = await res.json();
        } catch {
          console.error("Invalid JSON response");
          return;
        }

        if (!data || typeof data.score === "undefined") {
          console.error("Malformed vote response", data);
          return;
        }

        // Update score
        countEl.textContent = data.score === 0 ? "-" : data.score;

        // Reset button styles
        form.querySelectorAll(".vote-btn").forEach((btn) => {
          btn.classList.remove("text-blue-500", "text-orange-800");
          btn.classList.add("text-neutral-400");
        });

        // Highlight active vote
        if (data.user_vote === 1) {
          form
            .querySelector(".up")
            .classList.replace("text-neutral-400", "text-blue-500");
        } else if (data.user_vote === -1) {
          form
            .querySelector(".down")
            .classList.replace("text-neutral-400", "text-orange-800");
        }
      } catch (err) {
        console.error("Vote failed", err);
      }
    });
  });
});

function toggleReplies(btn) {
  const container = btn.nextElementSibling;

  if (!container) return;

  const isHidden = container.classList.contains("hidden");

  if (isHidden) {
    container.classList.remove("hidden");
    btn.innerText = btn.innerText.replace("Show", "Hide");
  } else {
    container.classList.add("hidden");
    btn.innerText = btn.innerText.replace("Hide", "Show");
  }
}

function toggleMenu(btn) {
  btn.nextElementSibling.classList.toggle("hidden");
}

document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("critique-root");
  if (!root) return;

  const postId = root.dataset.postId;
  loadCritiques(postId);
});

async function loadCritiques(postId) {
  const res = await fetch(`/api/critiques/${postId}`);
  const data = await res.json();

  const root = document.getElementById("critique-root");
  root.innerHTML = data.map(renderCritique).join("");
}

function renderCritique(c) {
  return `
    <div class="flex gap-3 mt-3">
      <div class="flex-1 bg-neutral-900 border border-neutral-800 rounded px-3 py-2">

        <div class="text-xs text-neutral-400 mb-1">
          ${c.user ? c.user.username : "Anonymous"}
          · ${new Date(c.created_at).toLocaleString()}
          ${c.is_author ? `<span class="text-green-500 ml-2 font-bold">Author</span>` : ""}
        </div>

        <p class="text-sm text-neutral-300 mb-2">
          ${escapeHtml(c.content)}
        </p>

        ${
          c.replies.length
            ? `<div class="ml-6 mt-3 border-l border-neutral-700 pl-3">
                ${c.replies.map(renderCritique).join("")}
               </div>`
            : ""
        }

      </div>
    </div>
  `;
}

function escapeHtml(text) {
  return text.replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      })[c],
  );
}
