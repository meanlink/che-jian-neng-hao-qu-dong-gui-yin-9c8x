import {api} from './client.js';
export const datasets={list:()=>api('/datasets'),get:id=>api('/datasets/'+id),create:data=>api('/datasets',{method:'POST',body:JSON.stringify(data)})};
export const jobs={list:()=>api('/jobs'),get:id=>api('/jobs/'+id),create:data=>api('/jobs',{method:'POST',body:JSON.stringify(data)}),approve:id=>api('/jobs/'+id+'/approve',{method:'POST'})};
export const reports={list:()=>api('/reports'),create:data=>api('/reports',{method:'POST',body:JSON.stringify(data)}),toggle:id=>api('/reports/'+id+'/toggle',{method:'POST'}),deliveries:()=>api('/deliveries')};
export const merge={
 overview:()=>api('/merge/overview'),
 sources:()=>api('/merge/sources'),
 upload:data=>api('/merge/sources',{method:'POST',body:JSON.stringify(data)}),
 samples:line=>api('/merge/samples?line='+encodeURIComponent(line)),
 publishes:line=>api('/merge/publishes?line='+encodeURIComponent(line)),
 arbitrate:data=>api('/merge/arbitrations',{method:'POST',body:JSON.stringify(data)}),
 confirm:id=>api('/merge/arbitrations/'+id+'/confirm',{method:'POST'}),
 publish:line=>api('/merge/publish',{method:'POST',body:JSON.stringify({line})}),
};
