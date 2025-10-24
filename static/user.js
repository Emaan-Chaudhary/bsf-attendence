function handleAction(event, message) {
    event.preventDefault(); // Prevent immediate submission

    const msgBox = document.getElementById("messageBox");
    const container = document.querySelector(".container");
    const buttons = document.querySelectorAll(".action-buttons button");
    const form = document.getElementById("actionForm");
    const welcomeText = document.querySelector(".welcome-text");

    // Hide buttons and dim welcome text
    buttons.forEach(btn => btn.style.display = "none");
    welcomeText.classList.add("dimmed");

    // Show message
    msgBox.innerHTML = `<div class="message">${message}</div>`;

    // Store action in hidden input
    if(document.getElementById("hiddenAction")) {
        document.getElementById("hiddenAction").value = event.target.value;
    }

    // Add animation class
    container.classList.add("message-active");

    // Wait 6 seconds for animation, then reset and submit form
    setTimeout(() => {
        // Clear message
        msgBox.innerHTML = "";

        // Show buttons again
        buttons.forEach(btn => btn.style.display = "block");

        // Restore welcome text
        welcomeText.classList.remove("dimmed");

        // Remove animation class
        container.classList.remove("message-active");

        // Reset inline styles
        container.style.background = "";
        container.style.boxShadow = "";
        container.style.transform = "";
        container.style.height = "";
        container.style.width = "";

        // Submit the form normally after animation
        form.submit();
    }, 6000);
}
