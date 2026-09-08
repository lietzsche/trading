function loadingFormStart(){
    document.querySelector('form').classList.add('d-none');
    document.querySelector('#loading').classList.remove('d-none');
}

function loadingFormEnd(){
    document.querySelector('#loading').classList.add('d-none');
    document.querySelector('form').classList.remove('d-none');
}