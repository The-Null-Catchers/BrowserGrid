const emit=(kind,data)=>console.log('@bg:'+JSON.stringify({kind,...data}));
module.exports=class BrowserGridReporter {
  onTestBegin(test,result){emit('test_start',{title:test.titlePath().join(' / '),retry:result.retry});}
  onTestEnd(test,result){emit('test_end',{title:test.titlePath().join(' / '),status:result.status,duration_ms:result.duration,retry:result.retry});}
  onStdOut(chunk){process.stdout.write(chunk);}
  onStdErr(chunk){process.stderr.write(chunk);}
};
