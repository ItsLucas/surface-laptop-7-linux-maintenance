#!/usr/bin/python3
from pathlib import Path
from collections import Counter
import os,select,struct,time,json,signal
running=True
def stop(*_):
 global running
 running=False
signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)
root=Path(__file__).resolve().parent
nodes=[n for n in Path('/sys/class/hidraw').glob('hidraw*') if '0000045E:00000C77' in (n/'device/uevent').read_text()]
assert len(nodes)==1
fd=os.open('/dev/'+nodes[0].name,os.O_RDONLY|os.O_NONBLOCK)
rows=[]
def hid(data,offset,end,depth=0):
 if depth>5 or offset+7>end:raise ValueError('bad HID frame')
 size=struct.unpack_from('<I',data,offset)[0];kind=data[offset+5]
 if size<7 or offset+size>end:raise ValueError('bad HID length')
 pos=offset+7;last=offset+size;result={'frame_type':kind,'length':size}
 if kind==0:
  children=[]
  while pos<last:
   child,pos=hid(data,pos,last,depth+1);children.append(child)
  result['children']=children
 elif kind==255:
  reports=[]
  while pos+4<=last:
   tag,flags,length=struct.unpack_from('<BBH',data,pos);pos+=4
   if pos+length>last:raise ValueError('bad subreport length')
   r={'type':tag,'flags':flags,'length':length}
   if tag==3 and length>=8:r['dimensions']=list(data[pos:pos+8])
   if tag==0x94 and length>=3:r['button_bit']=bool(data[pos+2]&2)
   if tag==0x25 and length:r['heat_min']=min(data[pos:pos+length]);r['heat_max']=max(data[pos:pos+length]);r['heat_sum']=sum(data[pos:pos+length])
   reports.append(r);pos+=length
  result['reports']=reports
 elif kind==1 and last-pos>=9:
  length=struct.unpack_from('<I',data,pos+5)[0];result['heat_bytes']=length
  if pos+9+length<=last and length:
   heat=data[pos+9:pos+9+length];result['heat_min']=min(heat);result['heat_max']=max(heat);result['heat_sum']=sum(heat)
 return result,last
end=time.monotonic()+180
print("LAYOUT_CAPTURE_READY",flush=True)
try:
 while running and time.monotonic()<end:
  ready,_,_=select.select([fd],[],[],.1)
  if not ready:continue
  packet=os.read(fd,65536)
  row={'epoch_ms':time.time()*1000,'report_id':packet[0] if packet else None,'length':len(packet)}
  if packet and packet[0] in [0x0a,0x0b,0x0c]:
   try:row['layout']=hid(packet,3,len(packet))[0]
   except Exception as e:row['error']=str(e)
  rows.append(row)
finally:os.close(fd)
p=root/('report-layout-'+time.strftime('%H%M%S')+'.json');p.write_text(json.dumps(rows,indent=2)+'\n');owner=root.stat();os.chown(p,owner.st_uid,owner.st_gid)
print('Saved',p,'packets',len(rows),flush=True)
shapes=Counter();examples={}
for row in rows:
 def strip_values(x):
  if isinstance(x,dict):return {k:strip_values(v) for k,v in x.items() if k not in ['epoch_ms','heat_min','heat_max','heat_sum','button_bit']}
  if isinstance(x,list):return [strip_values(v) for v in x]
  return x
 key=json.dumps(strip_values(row),sort_keys=True);shapes[key]+=1;examples[key]=row
for key,count in shapes.most_common(6):print(count,json.dumps(examples[key]))
