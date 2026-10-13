async function punch(kind){
 const status=document.getElementById('gpsmsg'), video=document.getElementById('camera');
 let stream;
 try{
  if(!window.isSecureContext) throw new Error('HTTPS is required for camera and GPS');
  status.textContent='Requesting location and camera...';
  const loc=await new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:true,timeout:20000,maximumAge:0}));
  if(loc.coords.accuracy>150) throw new Error('GPS accuracy is over 150m; move near a window and retry.');
  stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user'},audio:false});
  video.srcObject=stream;video.style.display='block';await video.play();
  status.textContent='Camera is ready. Confirm to capture a selfie and submit your '+kind+' time.';
  if(!confirm('Capture a selfie and submit clock '+kind+' now?'))return;
  const canvas=document.getElementById('snap');canvas.width=video.videoWidth;canvas.height=video.videoHeight;
  canvas.getContext('2d').drawImage(video,0,0);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',0.78));
  if(!blob)throw new Error('Unable to capture photo');
  const file=new File([blob],'attendance.jpg',{type:'image/jpeg'});
  const transfer=new DataTransfer();transfer.items.add(file);document.getElementById('photo').files=transfer.files;
  document.getElementById('kind').value=kind;document.getElementById('lat').value=loc.coords.latitude;
  document.getElementById('lng').value=loc.coords.longitude;document.getElementById('accuracy').value=loc.coords.accuracy;
  status.textContent='Submitting attendance...';document.getElementById('punchForm').submit();
 }catch(e){status.textContent='Attendance not submitted: '+e.message;}
 finally{if(stream)stream.getTracks().forEach(track=>track.stop());video.style.display='none';}
}
