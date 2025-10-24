const inputs = document.querySelectorAll('.login-section input');

inputs.forEach(input => {
    input.addEventListener('mouseenter', () => input.classList.add('hover-glow'));
    input.addEventListener('mouseleave', () => input.classList.remove('hover-glow'));
    input.addEventListener('focus', () => input.classList.add('hover-glow'));
    input.addEventListener('blur', () => input.classList.remove('hover-glow'));
});
const togglePassword = document.getElementById('togglePassword');
const password = document.getElementById('password');

togglePassword.addEventListener('click', function () {
    // toggle the type attribute
    const type = password.getAttribute('type') === 'password' ? 'text' : 'password';
    password.setAttribute('type', type);

    // toggle the eye icon
    this.classList.toggle('fa-eye-slash');
});
