function textCheck(ob){
    let text = ob.value;
    ob.value = text.replace(' ','');
}
function signUp(){
    loadingFormStart();
    let id = document.querySelector('#userId').value;
    let name = document.querySelector('#userName').value;
    let pwd = document.querySelector('#userPassword').value;
    let pwdCheck = document.querySelector('#userPasswordCheck').value;
    let email = document.querySelector('#userEmail').value;
    let phone = document.querySelector('#userPhone').value;
    let joinForm = document.querySelector('#joinForm');
    if(id === ''){
        alert('아이디를 입력해주세요');
        return;
    };
    if(name === ''){
        alert('아이디를 입력해주세요');
        return;
    };
    if(pwd === ''){
        alert('비밀번호를 입력해주세요');
        return;
    };
    if(pwdCheck === ''){
        alert('비밀번호를 확인해주세요');
        return;
    };
    if(pwd !== pwdCheck){
        alert('비밀번호와 비밀번호 확인 값이 다릅니다');
        return;
    }
    if (id.replace(' ','') === '' || name.replace(' ','') === '' || pwd.replace(' ','') === ''){
        alert('아이디, 이름, 비밀번호에는 공백을 넣을 수 없습니다.');
        return;
    }
    fetch("/join",{
        method:"POST",
        headers:{
            "Content-Type": "application/json",
        },
        body:JSON.stringify({
            userId:id,
            userName:name,
            userPassword:pwd,
            userEmail:email,
            userPhone:phone
        })
    }).then(data => data.json())
        .then(data => {
            loadingFormEnd();
            if(data.MSG === 'SUCCESS'){
                alert('가입되셨습니다.');
                location.href = '/';
            }else{
                alert(data.MSG);
            }
        })
    // joinForm.submit();
}
function back(){
    loadingFormStart();
    location.href="/";
}