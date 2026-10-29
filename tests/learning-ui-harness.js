'use strict';
module.exports=function(){
  const ids=new Map(),all=[],documentEvents={},windowEvents={};let doc;
  class Node{
    constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.dataset={};this.attributes={};this.style={};this.hidden=false;this.disabled=false;this.isConnected=true;this._text='';this.classList={add(){},remove(){},toggle(){}};all.push(this);}
    set textContent(v){this._text=String(v);this.children=[];}get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
    set innerHTML(_){throw Error('unsafe innerHTML');}
    append(...nodes){for(const n of nodes){this.children.push(n);n.parentElement=this;}}
    replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}
    setAttribute(k,v){this.attributes[k]=String(v);}getAttribute(k){return this.attributes[k];}removeAttribute(k){delete this.attributes[k];delete this[k];}
    addEventListener(k,fn){(this.listeners[k]||=[]).push(fn);}removeEventListener(k,fn){this.listeners[k]=(this.listeners[k]||[]).filter(f=>f!==fn);}
    fire(k,event={}){let result;event.target||=this;event.preventDefault||=()=>{};event.stopPropagation||=()=>{};for(const fn of this.listeners[k]||[])result=fn(event);return result;}
    focus(){doc.activeElement=this;}contains(n){return this===n||this.children.some(x=>x.contains?.(n));}
    getBoundingClientRect(){return {left:100,top:100,bottom:125,width:320,height:150};}scrollIntoView(){}
  }
  const el=id=>{if(!ids.has(id)){const n=new Node();n.id=id;ids.set(id,n);}return ids.get(id);};
  doc={activeElement:null,body:new Node('body'),documentElement:{clientWidth:1100,clientHeight:900},getElementById:el,createElement:tag=>new Node(tag),createTextNode:text=>({textContent:String(text)}),querySelector:()=>({content:'token'}),querySelectorAll:()=>[],addEventListener:(k,f)=>(documentEvents[k]||=[]).push(f)};
  const window={location:{href:'http://127.0.0.1:8765/?design=studio',assign(){}},innerWidth:1100,innerHeight:900,addEventListener:(k,f)=>(windowEvents[k]||=[]).push(f),setTimeout,clearTimeout};
  return {window,document:doc,el,all,node:tag=>new Node(tag),documentEvent(k,event){for(const f of documentEvents[k]||[])f(event);},windowEvent(k,event){for(const f of windowEvents[k]||[])f(event);}};
};
