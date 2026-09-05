// Run the actual browser functions without a server or third-party DOM package.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const src = fs.readFileSync(path.resolve(__dirname, '../../platform/CTFd/themes/ddps/assets/js/sql_challenge.js'), 'utf8');
const start = src.includes('async function readSQLResponse') ? src.indexOf('async function readSQLResponse') : src.indexOf('// Execute SQL Query');
const code = src.slice(start, src.indexOf('// Display Result'));
async function run(fn, {status=200, body={success:true,data:{status:'correct',message:'Sign In'}}, redirected=false, url='', clock='2026-09-05T03:01:00Z', behavior=false}={}) {
    const output = {fetches:0,expired:0,results:[],errors:[]};
    const button = {disabled:false, innerHTML:'Send'};
    class DeviceDate extends Date { constructor(...args) { super(...(args.length?args:[clock])); } }
    const ctx = {
        document:{getElementById(id) {
            if (id === 'challenge-submit' || id === 'challenge-execute') return button;
            if (id === 'challenge-id') return {value:'1'};
            if (id === 'challenge-input') return {value:'SELECT 1'};
            if (id === 'deadline-time') return {getAttribute(){return '2026-09-05T03:00:00Z'}};
        }},
        Date:DeviceDate, sqlEditor:null, CTFd:{user:{id:1,name:'synthetic'}}, init:{csrfNonce:'test'},
        behaviorLogger:behavior?{logEvent(){}}:null, console:{log(){},error(){}}, AbortController,
        setTimeout(){return 1}, clearTimeout(){},
        showSessionExpiredModal(){output.expired++}, showErrorToast(m){output.errors.push(m)},
        displayResult(r){output.results.push(r)},
        async fetch(){output.fetches++;return {ok:status<400,status,redirected,url, async text(){return typeof body === 'string'?body:JSON.stringify(body)}}},
    };
    await vm.runInNewContext(code+`\n${fn}()`,ctx);
    assert.equal(button.disabled,false);
    return output;
}
for (const fn of ['submitSQLChallenge','executeSQLQuery']) {
    test(`${fn}: clock and SQL text do not control admission/authentication`, async()=>{
        const r=await run(fn);
        assert.equal(r.fetches,1); assert.equal(r.expired,0); assert.equal(r.results.length,1);
    });
    test(`${fn}: submission limits are displayed`, async()=>{
        const r=await run(fn,{status:403,body:{success:true,data:{status:'ratelimited',message:'No tries remain'}}});
        assert.equal(r.expired,0); assert.equal(r.results[0].data.status,'ratelimited');
    });
    test(`${fn}: explicit authentication failures open the session dialog`, async()=>{
        assert.equal((await run(fn,{status:401,body:{}})).expired,1);
        assert.equal((await run(fn,{status:403,body:{data:{status:'authentication_required'}}})).expired,1);
        assert.equal((await run(fn,{redirected:true,url:'https://example.test/login'})).expired,1);
    });
    test(`${fn}: denied/invalid responses do not pretend the session expired`, async()=>{
        for(const body of ['<html>Sign In forbidden</html>',{success:false,errors:['Access denied']},null]) {
            const r=await run(fn,{status:403,body,behavior:true});
            assert.equal(r.expired,0); assert.ok(r.errors.length>0);
        }
    });
}

test('SQL error text is rendered as text, not markup',()=>{
    const render=src.slice(src.indexOf('function displayResult('),src.indexOf('// Render Table'));
    const status={};
    const document={getElementById(id){return id==='status-text'?status:{appendChild(){}}},createElement(){return {}}};
    vm.runInNewContext(render+`\ndisplayResult({data:{status:'incorrect',message:'Unknown column <b>marker</b>'}},true)`,{document});
    assert.equal(status.textContent,'Unknown column <b>marker</b>');
    assert.equal(status.innerHTML,undefined);
});
