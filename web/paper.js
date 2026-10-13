// O navegador recebe posições explícitas; CSS não decide as quebras do cupom.
(function(root){
  const FONTS={A:{cell:12,height:24,baseline:21},B:{cell:9,height:17,baseline:16}};
  const qrcode=root.qrcode||require('./qrcode.js');
  // atob devolve um caractere por byte, que o modo Byte grava sem conversão.
  function qrMatrix(line){
    const data=atob(line.data_base64);
    const mode=/^[0-9]+$/.test(data)?'Numeric':/^[0-9A-Z $%*+\-.\/:]+$/.test(data)?'Alphanumeric':'Byte';
    const qr=qrcode(0,line.error_level);
    qr.addData(data,mode);qr.make();
    const count=qr.getModuleCount(),border=4,size=count+border*2;
    return Array.from({length:size},(_,row)=>Array.from({length:size},(_,col)=>{
      const r=row-border,c=col-border;
      return r>=0&&r<count&&c>=0&&c<count&&qr.isDark(r,c)?'1':'0';
    }).join(''));
  }
  function layoutPaper(lines,warnings=[]){
    const paperWidth=48*FONTS.A.cell, rows=[];
    const offset=(align,width)=>align==='center'?(paperWidth-width)/2:align==='right'?paperWidth-width:0;
    for(const line of lines){
      if(line.type==='qr'){
        let matrix;
        try{matrix=qrMatrix(line)}
        catch{warnings.push('QR code não gerado: conteúdo excede a capacidade do QR code para este nível de correção.');continue}
        // Limite visual: 40% do papel, incluindo a margem branca do QR.
        const moduleSize=Math.min(line.module_size,(paperWidth*0.4)/matrix.length);
        const size=matrix.length*moduleSize;
        rows.push({chunks:[],width:paperWidth,height:size,qr:{matrix,moduleSize,size,x:offset(line.align,size)}});
        continue;
      }
      let chunks=[],used=0;
      function finish(){
        const glyphHeight=Math.max(FONTS.A.height,...chunks.map(s=>s.glyphHeight));
        const x=offset(line.align,used);
        for(const chunk of chunks)chunk.x+=x;
        rows.push({chunks,width:paperWidth,glyphHeight,height:Math.max(glyphHeight,line.spacing??30)});
        chunks=[];used=0;
      }
      for(const span of line.spans){
        const font=FONTS[span.font]||FONTS.A;
        const cell=font.cell*(span.width||1);
        const glyphHeight=font.height*(span.height||1);
        const baseline=font.baseline*(span.height||1);
        const chars=Array.from(span.text);
        let cursor=0;
        while(cursor<chars.length){
          let capacity=Math.floor((paperWidth-used)/cell);
          if(capacity===0){finish();capacity=Math.floor(paperWidth/cell)}
          const count=Math.min(capacity,chars.length-cursor);
          chunks.push({...span,text:chars.slice(cursor,cursor+count).join(''),x:used,
                       dotWidth:count*cell,glyphHeight,baseline});
          used+=count*cell;cursor+=count;
        }
      }
      finish();
    }
    return rows;
  }
  function renderPaper(container, lines){
    const ns='http://www.w3.org/2000/svg';
    const element=(name,attrs)=>{const e=document.createElementNS(ns,name);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);return e};
    const warnings=[];
    container.replaceChildren();
    for(const row of layoutPaper(lines,warnings)){
      const svg=element('svg',{viewBox:`0 0 ${row.width} ${row.height}`,class:'paper-row',role:'img'});
      if(row.qr){
        const {matrix,moduleSize,size,x}=row.qr;
        svg.classList.add('paper-qr');svg.setAttribute('aria-label','QR code');
        svg.append(element('rect',{x,y:0,width:size,height:size,fill:'#fff'}));
        let path='';
        for(let y=0;y<matrix.length;y++)for(let col=0;col<matrix[y].length;col++){
          if(matrix[y][col]==='1')path+=`M${x+col*moduleSize} ${y*moduleSize}h${moduleSize}v${moduleSize}h${-moduleSize}z`;
        }
        svg.append(element('path',{d:path,fill:'#000','shape-rendering':'crispEdges'}));
        container.append(svg);continue;
      }
      svg.setAttribute('aria-label',row.chunks.map(s=>s.text).join(''));
      for(const chunk of row.chunks){
        const top=row.glyphHeight-chunk.glyphHeight;
        const text=element('text',{x:chunk.x,y:top+chunk.baseline,
          'font-family':'Consolas, monospace','font-size':chunk.glyphHeight,
          'font-weight':chunk.bold?'700':'400',fill:'#171717',
          'font-style':chunk.italic?'italic':'normal',
          textLength:chunk.dotWidth,lengthAdjust:'spacingAndGlyphs','xml:space':'preserve'});
        text.style.whiteSpace='pre';text.textContent=chunk.text;
        svg.append(text);
        if(chunk.underline)svg.append(element('line',{x1:chunk.x,x2:chunk.x+chunk.dotWidth,y1:top+chunk.glyphHeight-1,y2:top+chunk.glyphHeight-1,stroke:'#171717','stroke-width':1}));
      }
      container.append(svg);
    }
    return warnings;
  }
  function paperPng(container,margin=24){
    const ns='http://www.w3.org/2000/svg';
    const page=document.createElementNS(ns,'svg');
    let width=0,height=margin;
    for(const row of container.querySelectorAll('svg.paper-row')){
      const [,,rowWidth,rowHeight]=row.getAttribute('viewBox').split(' ').map(Number);
      const copy=row.cloneNode(true);
      for(const [k,v] of Object.entries({x:margin,y:height,width:rowWidth,height:rowHeight}))copy.setAttribute(k,v);
      page.append(copy);
      width=Math.max(width,rowWidth+margin*2);height+=rowHeight;
    }
    height+=margin;
    const background=document.createElementNS(ns,'rect');
    for(const [k,v] of Object.entries({width:'100%',height:'100%',fill:'#fffdf4'}))background.setAttribute(k,v);
    page.prepend(background);
    for(const [k,v] of Object.entries({xmlns:ns,width,height,viewBox:`0 0 ${width} ${height}`}))page.setAttribute(k,v);
    const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(page)],{type:'image/svg+xml'}));
    return new Promise((resolve,reject)=>{
      const image=new Image();
      image.onload=()=>{
        const canvas=document.createElement('canvas');
        canvas.width=width;canvas.height=height;
        canvas.getContext('2d').drawImage(image,0,0);
        URL.revokeObjectURL(url);
        canvas.toBlob(blob=>blob?resolve(blob):reject(Error('Não foi possível gerar a imagem.')),'image/png');
      };
      image.onerror=()=>{URL.revokeObjectURL(url);reject(Error('Não foi possível gerar a imagem.'))};
      image.src=url;
    });
  }
  root.layoutPaper=layoutPaper;root.renderPaper=renderPaper;root.paperPng=paperPng;
  if(typeof module!=='undefined')module.exports={layoutPaper,qrMatrix};
})(typeof window!=='undefined'?window:globalThis);
