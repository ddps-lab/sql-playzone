const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const src = fs.readFileSync('platform/CTFd/themes/ddps/assets/js/sql_challenge_tracker.js','utf8');
function logger(fetch) {
 const context={fetch,console:{log(){},warn(){},error(){}},init:{csrfNonce:'test'}};
 const Class=vm.runInNewContext(src.slice(src.indexOf('class BehaviorLogger'),src.indexOf('let behaviorLogger'))+'\nBehaviorLogger',context);
 const result=Object.create(Class.prototype);
 Object.assign(result,{eventBuffer:[],batchSize:50,flushing:false});return result;
}
test('backlog drains in bounded ordered batches and retries temporary failure',async()=>{
 const batches=[];let fail=true;
 const actual=logger(async(url,options)=>{batches.push(JSON.parse(options.body).events);if(fail){fail=false;throw Error('offline')}return {ok:true}});
 actual.eventBuffer=Array.from({length:123},(_,i)=>i);
 await actual.flush();assert.equal(actual.eventBuffer.length,123);
 while(actual.eventBuffer.length)await actual.flush();
 assert.deepEqual(batches.map(b=>b.length),[50,50,50,23]);
 assert.deepEqual(batches.slice(1).flat(),Array.from({length:123},(_,i)=>i));
});
test('invalid event is isolated without losing later valid events',async()=>{
 const accepted=[];const actual=logger(async(url,options)=>{
  const events=JSON.parse(options.body).events;
  if(events.includes('bad'))return {ok:false,status:413};
  accepted.push(...events);return {ok:true};
 });actual.eventBuffer=['a','bad','b','c'];
 for(let i=0;i<20 && actual.eventBuffer.length;i++)await actual.flush();
 assert.equal(actual.eventBuffer.length,0);assert.deepEqual(accepted,['a','b','c']);
});
test('overlapping flush cannot overtake an in-flight batch',async()=>{
 let release;let calls=0;const actual=logger(()=>{calls++;return new Promise(resolve=>{release=resolve})});
 actual.eventBuffer=[1];const pending=actual.flush();actual.eventBuffer.push(2);await actual.flush();
 assert.equal(calls,1);release({ok:true});await pending;assert.deepEqual(actual.eventBuffer,[2]);
});
