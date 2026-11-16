/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
/** @typedef {{id:number,channel:string,stream:string,version:number,name:string,rows:number,status:string,created_by:string,created_at:number}} SourceBatch */
/** @typedef {{id:number,line:string,day:string,values:Object,provenance:Object,status:string,published_dataset_id:number|null,updated_at:number}} MergeSample */
/** @typedef {{id:number,line:string,day:string,field:string,chosen_value:number,reason:string,basis:Object,status:string,decided_by:string,confirmed_at:number}} Arbitration */
/** @typedef {{id:number,dataset_id:number,dataset:string,line:string,group_checksum:string,basis:Array,created_by:string,created_at:number}} PublishRecord */
export {};
