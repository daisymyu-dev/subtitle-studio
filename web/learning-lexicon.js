(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.LearningLexicon = factory();
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict';
  // Strict editorial IELTS-7-oriented allowlist: exactly 24 advanced IDs.
  // Not CEFR classification or investment advice; do not add basic matches as fallback.
  // Patterns are curated regex sources; Chinese patterns never include known bad literals.
  function entry(id, kind, term, pattern, meaning, chinese, note, gate, bad, warning) {
    return {id, kind, term, pattern, meaning, chinese: chinese.split('|').filter(Boolean), note,
      gate: gate || '', bad: bad || '', warning: warning || ''};
  }
  const finance = '(?:stocks?|markets?|investors?|funding|funds?|Fed|Treasur\\w*|bonds?|yields?|AI|tech|positioning|shorting|\\d+-year)';
  return [
    entry('glass-half','idiom','glass half full / glass half empty','glass[ -]half[ -](?:full(?:\\s*,\\s*glass[ -]half[ -]empty)?|empty)','半杯水心态：同一情况可从乐观或悲观角度看','半满半空的玻璃杯|半满的玻璃杯|半空的玻璃杯','成对使用表示观察角度不同，并非描述杯子的容量。'),
    entry('natural-governor','idiom','natural governor','natural governor','自发约束机制；此处指融资成本对过度扩张的制约','自发约束机制|自然制约机制','governor 在此比喻调节、限制扩张的机制，不是政治人物。','','统治者|州长','此处不是“统治者／州长”，而是融资市场形成的自发约束机制。'),
    entry('nimby','idiom','not in my backyard / NIMBY','not in my backyard|NIMBY','邻避效应：支持某类设施，但反对建在自家附近','邻避效应|邻避心理','常用于数据中心、能源和公共设施选址争议。','','不在我后院|不在我的后院|不要在我家后院','直译“后院”会遗漏邻避效应：不愿相关设施建在自己居住地附近。'),
    entry('coiled-spring','idiom','coiled spring','coiled spring','蓄势待发的状态；像被压紧的弹簧','蓄势待发|压紧的弹簧|压缩的弹簧|弹簧','市场评论中的比喻，表达潜在反弹动能，并不保证上涨。'),
    entry('buy-the-dip','finance','buy the dip','buy(?:ing)? (?:this|the) (?:AI )?dip','逢回调买入；此处指买入下跌后的人工智能相关股票','逢回调买入|逢低买入|买入人工智能下跌的股票','dip 指价格回落；这是说话人的交易观点，并非买入建议。','','人工智能浸|浸泡|蘸酱','“人工智能浸”是误译；buy the AI dip 指在人工智能相关股票回调时买入。'),
    entry('tailwinds','finance','tailwinds','tailwinds?','有利因素；推动市场或业务发展的助力','有利因素|利好因素','金融语境中的“顺风”是比喻，不是天气预报。',finance,'顺风','这里的 tailwinds 指市场的有利因素，不是字面上的顺风。'),
    entry('otherworldly','vocab','otherworldly','otherworldly','超乎寻常的；此处形容突破惊人','超凡脱俗|超乎寻常','带有夸张赞叹色彩，并非声称技术来自另一个世界。'),
    entry('astounding','vocab','astounding','astounding','令人惊叹的；惊人的','令人震惊|令人惊叹|惊人','强调出乎意料的程度，可修饰数字、成就或发现。'),
    entry('bifurcated','vocab','bifurcated','bifurcated','分成两支的；此处指情绪出现两极分化','两极分化|出现了分歧|分歧','比 divided 更强调分成两个方向；并非任何分歧都严格只有两派。'),
    entry('ensued','vocab','ensued','ensued','随后发生；接着出现','随之而来|随后发生','正式叙述用语，常以事件作主语，不直接证明因果关系。'),
    entry('historical-analogs','vocab','historical analogs','historical analog(?:ue)?s?','历史上的相似案例；历史类比','历史类比|历史上有类似的事实|历史上的相似案例','类比用于比较相似条件，不能证明历史必然重演。'),
    entry('irrational-exuberance','finance','irrational exuberance','irrational exuberance','非理性繁荣；缺乏基本面支撑的过度乐观','非理性繁荣','常用于资产价格和投资情绪，exuberance 强调过度热情。'),
    entry('preemptive-tightening','finance','preemptive policy tightening','preemptive policy tightening','预防性政策收紧；在通胀明显出现前先行紧缩','先发制人的政策紧缩|预防性政策收紧','preemptive 强调提前防范；tightening 不仅限于加息。'),
    entry('qoq-revenue','finance','quarter-over-quarter revenue growth','quarter[ -]over[ -]quarter revenue growth','营收环比增长；本季度相对上一季度的营收增幅','季度环比收入增长|营收环比增长','环比比较相邻季度，不是与去年同季比较的同比。'),
    entry('priced-in','finance','priced in','(?:getting |gets? |being |already )?priced in','已反映在价格中；市场价格已计入相关预期','已反映在价格中|已计入价格|已被市场消化','priced in 指信息被价格吸收，不是单纯给某物标价。','','被定价|定价了','“被定价”不够准确：这里指相关风险或预期已经反映在市场价格中。'),
    entry('de-risking','finance','de-risking','de[ -]risk(?:ing)?','降低风险敞口；减少高风险持仓','降低风险敞口|去风险化|风险将会普遍降低','不是消除所有风险，常指削减某类资产或策略的暴露。',finance),
    entry('long-short-positioning','finance','long short positioning','long[ -]short positioning','多空持仓配置；多头与空头的仓位分布','多空持仓配置|多空仓位','positioning 指市场参与者的仓位结构，不是空间定位。','','多空定位','“多空定位”应理解为多空持仓配置，而不是位置或品牌定位。'),
    entry('capitulation','finance','capitulation','capitulation','恐慌性抛售；投资者放弃抵抗、集中减仓','恐慌性抛售|恐慌抛售','金融评论中比喻投资者认输离场；不能据此确认市场已见底。','(?:short(?:ing)?|positioning|stocks?)','投降','此处是市场语境下的恐慌性抛售，不是一般意义上的投降。'),
    entry('dovish','finance','dovish','dovish','鸽派的；倾向较宽松的货币政策','鸽派|倾向宽松','描述政策倾向或市场解读，不表示已经降息。'),
    entry('style-tilt','finance','style tilt','style tilt','风格偏向；组合向某种投资风格倾斜','风格倾斜|风格偏向','例如偏向成长或价值，tilt 表示相对基准的配置偏好。'),
    entry('frontier-models','vocab','frontier models','frontier models?','前沿模型；处于当前能力前沿的人工智能模型','前沿模型','frontier 修饰技术能力边界，不是地理边境。'),
    entry('revenue-per-worker','finance','revenue per worker','revenue per worker','人均营收；每位员工对应的企业营收','人均营收','不是员工工资；是总营收除以员工人数的指标。','','每名工人的收入|每个工人的收入','这里指企业人均营收，不是每名工人领取的工资或个人收入。'),
    entry('cds-widen','finance','credit default swaps widen','credit default swaps widen','信用违约掉期利差扩大；信用保护变贵','信用违约掉期利差扩大','这里 widen 通常指利差扩大，反映市场要求更高风险补偿，不是合约数量变多。','','信用违约掉期扩大','这里扩大的是信用违约掉期的利差／风险保护成本，不是掉期本身的体积。'),
    entry('treasury-issuance','finance','treasury issuance','treasury issuance','国债发行；此处指美国国债的发行规模','国债发行','issuance 指发行活动或发行量，不是国债的市场成交量。')
  ];
});
