// app.js
// 전역 상태 관리와 화면 전환 로직

const API_BASE = '/api';

let state = {
  products: [],
  cart: [],
  user: null,
};

function $(selector) {return document.querySelector(selector);}
function $$(el, selector) {return el.querySelectorAll(selector);}

// 화면 전환
function showSection(sectionId) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active','section--active'));
  const sec = $(`#${sectionId}`);
  if (sec) {sec.classList.add('section--active');}
}

function initNav() {
  $('#nav-home').addEventListener('click', () => showSection('home'));
  $('#nav-cart').addEventListener('click', () => showSection('cart'));
}

// 로딩 스피너 (간단 구현)
function setLoading(isLoading) {
  // placeholder: could add overlay
  console.log('loading:', isLoading);
}

async function fetchProducts() {
  setLoading(true);
  try {
    const res = await fetch(`${API_BASE}/products`);
    const data = await res.json();
    if (data.ok) {
      state.products = data.data;
      renderProductGrid();
    } else {alert(data.error);}
  } catch(e){alert('네트워크 오류');}
  setLoading(false);
}

function renderProductGrid() {
  const grid = $('#product-grid');
  grid.innerHTML = '';
  state.products.forEach(p => {
    const card = document.createElement('div');
    card.className = 'product-card';
    // 이미지 대신 배경 그라디언트
    const imgDiv = document.createElement('div');
    imgDiv.style.height='120px';
    imgDiv.style.background='linear-gradient(45deg, var(--color-primary), var(--color-accent))';
    imgDiv.setAttribute('role','img');
    imgDiv.setAttribute('aria-label', p.name);
    const name = document.createElement('h3');
    name.textContent = p.name;
    const price = document.createElement('p');
    price.textContent = `₩${p.price}`;
    const btn = document.createElement('button');
    btn.className='btn btn--primary';
    btn.textContent='장바구니에 담기';
    btn.addEventListener('click',()=>addToCart(p.id));
    card.appendChild(imgDiv);
    card.appendChild(name);
    card.appendChild(price);
    card.appendChild(btn);
    grid.appendChild(card);
  });
}

async function addToCart(productId) {
  if (!state.user) {alert('로그인 필요'); return;}
  try {
    const res = await fetch(`${API_BASE}/cart/add`,{
      method:'POST',
      headers:{'Content-Type':'application/json','Authorization':`Bearer ${state.user.sessionToken}`},
      body:JSON.stringify({productId, quantity:1})
    });
    const data = await res.json();
    if (data.ok) {state.cart = data.data.items; renderCart();}
    else {alert(data.error);}
  } catch(e){alert('네트워크 오류');}
}

function renderCart() {
  const cartDiv = $('#cart-items');
  cartDiv.innerHTML='';
  let total=0;
  state.cart.forEach(item=>{
    const div=document.createElement('div');
    div.className='cart-item';
    div.textContent=`${item.name} x ${item.quantity} = ₩${item.subtotal}`;
    cartDiv.appendChild(div);
    total+=item.subtotal;
  });
  $('#cart-total').textContent=`총합: ₩${total}`;
}

async function login(event){
  event.preventDefault();
  const email=$('#email').value.trim();
  const pw=$('#password').value;
  try {
    const res=await fetch(`${API_BASE}/login`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password:pw})});
    const data=await res.json();
    if(data.ok){state.user=data.data; $('#login-error').textContent=''; showSection('home'); fetchProducts();}
    else {$('#login-error').textContent=data.error;}
  } catch(e){$('#login-error').textContent='네트워크 오류';}
}

async function submitContact(event){
  event.preventDefault();
  const name=$('#c-name').value.trim();
  const email=$('#c-email').value.trim();
  const subject=$('#c-subject').value.trim();
  const message=$('#c-message').value.trim();
  if(!name||!email||!subject||!message){$('#contact-msg').textContent='모든 필드가 필요합니다.';return;}
  try {
    const res=await fetch(`${API_BASE}/contact`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,email,subject,message})});
    const data=await res.json();
    if(data.ok){$('#contact-msg').textContent='문의가 정상적으로 접수되었습니다';}
    else {$('#contact-msg').textContent=data.error;}
  } catch(e){$('#contact-msg').textContent='네트워크 오류';}
}

function init() {
  initNav();
  $('#login-form').addEventListener('submit', login);
  $('#contact-form').addEventListener('submit', submitContact);
  // 초기 화면은 home but need products; if logged in, fetchProducts later.
  showSection('home');
}

document.addEventListener('DOMContentLoaded', init);
