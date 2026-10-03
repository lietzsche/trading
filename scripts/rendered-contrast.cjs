// Sample the rendered background with text paint disabled, including gradients.
const zlib=require('node:zlib');
function decodePNG(buffer){
 let offset=8,width,height,channels;const chunks=[];
 while(offset<buffer.length){const length=buffer.readUInt32BE(offset),type=buffer.toString('ascii',offset+4,offset+8),data=buffer.subarray(offset+8,offset+8+length);offset+=length+12;
  if(type==='IHDR'){width=data.readUInt32BE(0);height=data.readUInt32BE(4);if(data[8]!==8||data[12]!==0)throw Error('Unsupported PNG format');channels=data[9]===6?4:data[9]===2?3:0;if(!channels)throw Error('Unsupported PNG color');}
  if(type==='IDAT')chunks.push(data);if(type==='IEND')break;
 }
 const raw=zlib.inflateSync(Buffer.concat(chunks)),stride=width*channels,pixels=Buffer.alloc(height*stride);let source=0;
 for(let y=0;y<height;y++){const filter=raw[source++];for(let x=0;x<stride;x++){const a=x>=channels?pixels[y*stride+x-channels]:0,b=y?pixels[(y-1)*stride+x]:0,c=y&&x>=channels?pixels[(y-1)*stride+x-channels]:0;let prediction=0;
  if(filter===1)prediction=a;else if(filter===2)prediction=b;else if(filter===3)prediction=Math.floor((a+b)/2);else if(filter===4){const p=a+b-c,pa=Math.abs(p-a),pb=Math.abs(p-b),pc=Math.abs(p-c);prediction=pa<=pb&&pa<=pc?a:pb<=pc?b:c;}else if(filter!==0)throw Error('Unsupported PNG filter');pixels[y*stride+x]=(raw[source++]+prediction)&255;
 }}return {pixel:(x,y)=>[...pixels.subarray((Math.floor(y)*width+Math.floor(x))*channels,(Math.floor(y)*width+Math.floor(x))*channels+3)]};
}
const luminance=rgb=>rgb.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
async function renderedContrast(page){
 const nodes=await page.evaluate(()=>{
  const scope=document.querySelector('[role="dialog"]')||document.body,walker=document.createTreeWalker(scope,NodeFilter.SHOW_TEXT),result=[];let node;
  while(node=walker.nextNode()){
   if(!node.textContent.trim())continue;const el=node.parentElement;if(!el||!el.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})||el.closest('script,style,option,button:disabled,input:disabled,select:disabled,textarea:disabled'))continue;
   const style=getComputedStyle(el);let opacity=1;for(let parent=el;parent;parent=parent.parentElement)opacity*=Number(getComputedStyle(parent).opacity);
   const color=style.color.match(/[\d.]+/g)?.map(Number);if(!color||color.length<3)continue;
   const range=document.createRange();range.selectNodeContents(node);
   for(const rect of range.getClientRects()){
    if(!rect.width||!rect.height||rect.bottom<0||rect.top>innerHeight||rect.left<0||rect.right>innerWidth)continue;
    const x=Math.min(innerWidth-1,Math.max(0,rect.left+rect.width/2)),y=Math.min(innerHeight-1,Math.max(0,rect.top+rect.height/2)),hit=document.elementFromPoint(x,y);
    if(!hit||!(el.contains(hit)||hit.contains(el)))continue;
    result.push({text:node.textContent.trim().slice(0,65),selector:el.className,color,opacity,x,y});
   }
  }return result;
 });
 const hidden=await page.addStyleTag({content:'* { -webkit-text-fill-color: transparent; text-shadow: none; }'});
 let pixels;try{pixels=decodePNG(await page.screenshot({animations:'disabled',scale:'css'}))}finally{await hidden.evaluate(el=>el.remove())}
 const results=nodes.map(node=>{const bg=pixels.pixel(node.x,node.y),alpha=(node.color[3]??1)*node.opacity,fg=node.color.slice(0,3).map((v,i)=>v*alpha+bg[i]*(1-alpha)),a=luminance(fg),b=luminance(bg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);return {...node,bg,ratio}});
 return {checked:results.length,minRatio:Math.min(...results.map(n=>n.ratio)),failures:results.filter(n=>n.ratio<4.5)};
}
module.exports={renderedContrast};
