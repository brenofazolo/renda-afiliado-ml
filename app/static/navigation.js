document.addEventListener("DOMContentLoaded", () => {
  const logo = document.querySelector("header .brand img");
  if (!logo) return;
  logo.style.cursor = "pointer";
  logo.setAttribute("title", "Voltar para Descobrir");
  logo.setAttribute("tabindex", "0");
  const goHome = () => window.location.assign("/");
  logo.addEventListener("click", goHome);
  logo.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") goHome();
  });
});
